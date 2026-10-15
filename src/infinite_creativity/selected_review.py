"""Selected large originals: request-only staging and client-carried digests."""
import base64,hashlib,json,posixpath,re,shutil,tempfile
from pathlib import Path,PurePosixPath
from .live import seal,unseal,file_fingerprint
from .policy import LICENSES,acceptable,review_terms
from .review_limits import profile,limits,progress
from .specialized_media import NATIVE,LAYERED,MESH,review_path

SUPPORTED=NATIVE|LAYERED|MESH|{'gltf','glb','png','jpg','jpeg','bmp','tif','tiff','dds','wav','ogg','mp3','flac','m4a','aac','aiff','aif','opus','mp4','webm','mov','mkv','avi','gif','webp','apng','svg','exr','hdr'}
IMAGE={'png','jpg','jpeg','bmp','tif','tiff','dds','webp','exr','hdr'}

def member_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or value.startswith('/') or '..' in PurePosixPath(value).parts:
        raise ValueError('Unsafe scoped member path')
    if not acceptable(value) or review_terms(value):raise ValueError('Scoped member name violates content policy')
    return str(PurePosixPath(value))

def usable(a):
    if (a['license'] not in LICENSES and not a.get('end_product_only_verified')) or not a.get('license_url') or 'required-for-originals' in a.get('original_access',''):
        raise ValueError('Selected original has no current reusable public rights/access scope')

def archive_entries(library,a,file):
    usable(a)
    from .content import ContentCache
    container=a.get('containers',{}).get(file.get('container_id'))
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-archive-list-') as directory:
        cache=ContentCache(directory)
        archive=cache.multipart_zip(container['parts']) if container and container['type']=='split-zip' else cache.remote_zip(file['url'])
        with archive as z:
            entries=z.infolist()
            if len(entries)>10000:raise ValueError('Archive member inventory exceeds bounded navigation budget')
            result=[]
            for v in entries:
                if v.is_dir():continue
                try:name=member_path(v.filename)
                except ValueError:continue
                result.append({'entry':name,'bytes':v.file_size,'crc32':v.CRC,'format':PurePosixPath(name).suffix.lstrip('.').lower()})
            return result

def archive_selection(library,a,selection):
    file=next((f for f in a.get('files',[]) if file_fingerprint(f)==selection['file']),None)
    if not file or Path(file['filename']).suffix.lower()!='.zip':raise ValueError('Current archive manifest changed; reopen the archive')
    name=member_path(selection['entry']);entries=archive_entries(library,a,file)
    chosen=next((v for v in entries if v['entry']==name),None)
    if not chosen or chosen['format'] not in SUPPORTED:raise ValueError('Selected archive member is unavailable or has no complete reviewer')
    folder=str(PurePosixPath(name).parent)
    scope=[v for v in entries if v==chosen or str(PurePosixPath(v['entry']).parent)==folder and v['format'] in IMAGE|{'bin','mtl','txt','md'}]
    if len(scope)>48:raise ValueError('Selected archive dependency scope exceeds 48 files')
    records=[{**file,'filename':PurePosixPath(v['entry']).name,'relative_path':v['entry'],'archive_entry':v['entry'],'bytes':v['bytes'],'crc32':v['crc32'],'role':'main' if v==chosen else 'dependency'} for v in scope]
    # Container checksum describes the ZIP, not an individual member.
    for f in records:
        for k in ('sha','sha256','md5','format'):f.pop(k,None)
    return {**a,'files':records,'formats':[chosen['format']],'selected_archive_entry':name}

def open_archive(library,aid,file_id='',entry='',offset=0,limit=100):
    if offset<0 or not 1<=limit<=200:raise ValueError('Invalid archive navigation window')
    with library.content(aid,selected_review=True) as (lib,local,a):
        files=lib.files(local)['files'];file=next((f for f in files if f['id']==file_id),None) if file_id else next((f for f in files if f['format']=='zip'),None)
        if not file or file['format']!='zip':raise ValueError('Choose a current ZIP file ID from candidate_asset_files')
        entries=archive_entries(library,a,file)
        if entry:
            entry=member_path(entry)
            if not any(v['entry']==entry for v in entries):raise ValueError('Member not present in the fresh archive inventory')
            locator=unseal(aid,'asset');locator.pop('review',None);locator['selection']={'file':file['_review_key'],'entry':entry}
            return {'asset_id':seal('asset',locator),'state':'pending-original-review','entry':entry,'actions':['candidate_asset_files','review_asset_media'],'storage':'Fresh archive inventory only; no selected member bytes emitted or stored'}
        return {'members':entries[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(entries) else None,'member_count':len(entries),'scope':'Current bounded ZIP directory, excluding unsafe/sexual names; this is not an admitted asset count','actions':['open_asset_archive'],'storage':'No directory or member content retained'}

def review(library,aid,file_id='',callback=None):
    with library.content(aid,selected_review=True) as (lib,local,a):
        usable(a);manifest=lib.files(local)['files']
        candidates=[f for f in manifest if f['format'] in SUPPORTED and f.get('role') in {'main','variant'}]
        previous=unseal(aid,'asset').get('review')
        if previous and not file_id:
            library.get(aid)
            candidates=[f for f in candidates if f['_review_key'] in previous['files']]
        main=next((f for f in candidates if f['id']==file_id),None) if file_id else min(candidates,key=lambda f:(f['format'] not in {'glb','gltf'},f.get('bytes') or 512*1024*1024),default=None)
        if not main:raise ValueError('Choose a supported original ID from candidate_asset_files; ZIP packs use open_asset_archive first')
        bundle=main.get('bundle_key')
        scope=[main]+[f for f in manifest if f['id']!=main['id'] and f.get('role') in {'dependency','license','provenance'} and (not bundle or not f.get('bundle_key') or f['bundle_key']==bundle)]
        if len(scope)>48:raise ValueError('Selected licensed dependency scope exceeds 48 files')
        with tempfile.TemporaryDirectory(prefix='infinite-creativity-selected-review-') as directory,profile('extended',callback):
            root=Path(directory);staged={};receipts={};total=0
            for f in scope:
                progress(total,limits()['bytes'],'Fetching scoped original/dependency '+f['filename'][:100])
                relative=member_path(f.get('relative_path') or f['filename']);target=(root/relative).resolve()
                if not target.is_relative_to(root.resolve()):raise ValueError('Dependency leaves scoped staging')
                if relative in staged:raise ValueError('Ambiguous duplicate dependency destination')
                remaining=limits()['bytes']-total
                if remaining<=0 or (f.get('bytes') or 0)>remaining:raise ValueError('Selected bundle exceeds 512 MiB request byte budget')
                result=lib.file(local,f['id'],remaining);total+=result['bytes'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(result['path'],target)
                staged[relative]=(target,f,result)
                receipts[f['_review_key']]={'sha256':result['sha256'],'bytes':result['bytes']}
            path=next(v[0] for v in staged.values() if v[1]['id']==main['id'])
            # Never let a renderer resolve unlisted local/remote dependencies.
            if main['format']=='obj':
                names=[]
                for line in path.read_text(encoding='utf-8-sig').splitlines():
                    if line.startswith('mtllib '):names.extend(line[7:].strip().split())
                for name in names:
                    target=(path.parent/member_path(name)).resolve()
                    if str(target) not in {str(v[0]) for v in staged.values()}:raise ValueError('OBJ material dependency is not in the current licensed manifest')
            for relative,(target,f,result) in staged.items():
                if f['format']=='mtl':
                    for line in target.read_text(encoding='utf-8-sig').splitlines():
                        if re.match(r'\s*(?:map_\w+|bump|disp|decal)\s',line,re.I):
                            name=line.split()[-1];dep=(target.parent/member_path(name)).resolve()
                            if str(dep) not in {str(v[0]) for v in staged.values()}:raise ValueError('MTL texture dependency is not in the current licensed manifest')
            from .live_admission import screener,model_path
            progress(total,total,'Decoding and inspecting selected original '+main['filename'][:100])
            classifier=None if main['format'] in {'wav','ogg','mp3','flac','m4a','aac','aiff','aif','opus'} else screener(str(model_path()))
            evidence=review_path(path,main['format'],classifier,directory)
            converted=evidence.pop('_converted_glb',None)
            preview_bytes=evidence.pop('_preview_bytes',None)
            # Also inspect declared image dependencies that a converter might
            # omit from the visible scene. Raw buffers are bound by GLTF review.
            for target,f,result in staged.values():
                if f['id']!=main['id'] and f['format'] in IMAGE:review_path(target,f['format'],classifier,directory)
                elif f['id']!=main['id'] and f['format'] not in IMAGE|{'bin','mtl','txt','md'} and f.get('role') not in {'license','provenance'}:
                    raise ValueError('Declared dependency requires its own complete original reviewer')
            progress(1,1,'Selected original and scoped dependencies reviewed; request-only staging will be removed')
            locator=unseal(aid,'asset');locator['review']={'metadata':a['_source_metadata'],'files':receipts,'scope':evidence['scope']}
            reviewed_id=seal('asset',locator)
            if len(reviewed_id)>24000:raise ValueError('Selected bundle exceeds bounded client receipt budget')
            preview={'_preview_png':base64.b64encode(preview_bytes).decode()} if preview_bytes else {}
            if converted or main['format']=='glb':
                from .live_media_review import render_glb_preview,image_check
                from PIL import Image
                import io
                pixels=render_glb_preview(Path(converted or path).read_bytes())
                with Image.open(io.BytesIO(pixels)) as im:image_check(im,classifier,directory,'selected-preview')
                preview={'_preview_png':base64.b64encode(pixels).decode()}
            return {'asset_id':reviewed_id,'state':'selected-original-screened','selected_file_id':main['id'],'format':main['format'],'review':evidence,'reviewed_files':len(receipts),'reviewed_bytes':total,'license':a['license'],'license_url':a['license_url'],'actions':['get_library_item','asset_files','read_asset_file'],**preview,'storage':'No original, metadata index or verdict retained. Client locator carries signed digests only. Every subsequent call fetches current metadata and verifies exact original bytes again.','limits':'Bounded automatic review, not a guarantee of perfect safety or artistic quality. Unreviewed variants are unavailable through this locator. Chunk delivery re-fetches the full reviewed file to verify its digest; there is no cross-call original cache.'}
