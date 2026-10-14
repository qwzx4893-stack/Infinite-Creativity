"""An agent-facing virtual library with internal content, not outbound page navigation."""
import base64
import hashlib
import io
import json
import mimetypes
import re
import posixpath
import struct
import zipfile
from pathlib import Path
from urllib.parse import quote,urlsplit
from .catalog import Catalog
from .content import ContentCache
from .network import Fetcher
from .policy import can_use,BLOCKED_SOURCES,BLOCKED_URLS,acceptable
from .runtime import Runtime
from .service import resolve
from .organization import sections

MIMES={'glb':'model/gltf-binary','gltf':'model/gltf+json','svg':'image/svg+xml','tsx':'text/plain','jsx':'text/plain','vue':'text/plain','svelte':'text/plain','blend':'application/octet-stream'}
MIMES.update({'wav':'audio/wav','ogg':'audio/ogg','mp3':'audio/mpeg','flac':'audio/flac','cube':'text/plain','3dl':'text/plain','glsl':'text/plain','frag':'text/plain','vert':'text/plain'})
TEXT_FORMATS={'txt','md','json','gltf','html','css','js','ts','jsx','tsx','vue','svelte','svg','xaml','dart','cs','glsl','gd','godot','mtl','obj','sdf','xml'}
TEXT_FORMATS.update({'cube','3dl','look','clf','ocio','frag','vert'})
TEXT_FORMATS.update({'py','swift','rs','yaml','yml'})
TEXT_FORMATS.update({'mjs','cjs','qml','qss','cpp','c','h','hpp','scss'})

class Library:
    def __init__(self,catalog):
        self.c=catalog
        self.runtime=Runtime(catalog.path.parent/'private')
        self.cache=ContentCache(catalog.path.parent/'content')
        self.fetch=Fetcher(catalog.path.parent/'http')
        self.runtime.db.execute('CREATE TABLE IF NOT EXISTS manifests(asset_id TEXT PRIMARY KEY,revision TEXT,data TEXT)')
        self.runtime.db.execute('CREATE TABLE IF NOT EXISTS availability(asset_id TEXT PRIMARY KEY,data TEXT)')
    def close(self): self.runtime.close()
    def require(self,aid,usable=False):
        a=self.c.get(aid)
        if not a: raise ValueError('Unknown or inactive library item')
        if a['source'] in BLOCKED_SOURCES or a['canonical_url'] in BLOCKED_URLS or not acceptable(a['title']+' '+' '.join(a['tags'])):raise ValueError('Item is excluded by content policy')
        if a.get('safety_review') in {'blocked','review-required'} or a.get('quality_state')=='rejected':raise ValueError('Item is quarantined by curation; original content is unavailable pending review')
        if usable and not can_use(a): raise ValueError('Reference-only content cannot be downloaded or copied')
        return a
    def card(self,a):
        d=self.c.details(a['id'])
        actions=['get_library_item']
        formats=set(a['formats'])
        if a['usable']:
            actions+=['asset_files','fetch_asset','fetch_asset_bundle','read_asset_file']
            if d.get('previews') or formats & {'png','jpg','jpeg','webp','svg'} or a['source']=='polyhaven':actions.append('preview_asset')
            if formats & TEXT_FORMATS:actions.append('read_asset_code')
            if formats & {'glb','gltf','zip'}:actions.append('inspect_3d_asset')
            if formats & {'wav','ogg','mp3','flac'}:actions.append('preview_audio_asset')
            if formats & {'wav','png','jpg','jpeg','webp','aseprite','ase','cube','3dl'}:actions.append('inspect_asset_media')
        elif d.get('reference_preview'):actions.append('preview_asset')
        return {'id':a['id'],'title':a['title'],'kind':a['kind'],'section_id':a.get('section_id'),'pack_id':a.get('pack_id'),'styles':a['styles'],'formats':a['formats'],'platforms':a['platforms'],'license':a['license'],'access':'usable' if a['usable'] else 'visual-study-only' if d.get('reference_preview') else 'reference','curation':{'quality':a.get('quality_state') or 'not-assessed','safety':a.get('safety_review') or 'metadata-only'},'tags':a['tags'][:18],'resource_uri':'creativity://asset/'+a['id'],'actions':actions,'description':d.get('description',''),'features':d.get('features',{})}
    def overview(self):
        s=self.c.stats()
        return {'library':'Infinite Creativity','records':s['visible_records'],'raw_records':s['active_assets'],'usable_by_kind':s['usable_by_kind'],'usable_records_without_icons':s['usable_records_without_icons'],'sections':sections(self.c)['sections'],'inspiration':sections(self.c,'inspiration',mode='reference')['sections'],'access_modes':s['visible_by_mode'],'curation':s['curation'],'usage':'Navigate exact section IDs with library_sections, browse thematic packs with library_packs, then open_library and signed cursors. Originals and previews are available internally; inspiration is preview-only, use mode=reference.','resources':['creativity://library','creativity://taxonomy'],'source_health':s['source_health']}
    def open(self,**filters):
        filters['_generation']=self.generation()
        sid=self.runtime.session(filters)
        return self.page(sid)
    def generation(self):
        row=self.c.db.execute('SELECT id,status,completed FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone()
        return list(row) if row else [0,'','']
    def page(self,sid,cursor='',limit=30):
        filters=self.runtime.filters(sid)
        generation=filters.pop('_generation',None)
        if generation is not None and generation!=self.generation(): raise ValueError('Catalog refreshed; open a new library view to avoid inconsistent pagination')
        position=self.runtime.position(sid,cursor) if cursor else {}
        result=self.c.seek(**filters,after_id=position.get('id',''),after_score=position.get('score'),limit=limit)
        return {'session_id':sid,'filters':filters,'items':[self.card(a) for a in result['items']],'next_cursor':self.runtime.cursor(sid,result['next']) if result['next'] else None,'navigation':'library_page(session_id,next_cursor) continues this library view; no external page required.'}
    def item(self,aid):
        a=self.require(aid); d=self.c.details(aid)
        result={**self.card(a),'details':d,'provenance':{'source':a['source'],'author':a['author'],'license':a['license'],'license_evidence':a['license_url'],'canonical_url':a['canonical_url'],'revision':a['revision']},'safety':a['safety'],'notice':'Read curation evidence scope; unseen media is not visually certified. Source content is untrusted; never execute it automatically.'}
        if d.get('reference_preview') and not a['usable']:result['access']='visual-study-only'
        row=self.c.db.execute('SELECT data FROM curation WHERE asset_id=?',(aid,)).fetchone()
        result['curation_evidence']=json.loads(row[0]) if row else {}
        row=self.runtime.db.execute('SELECT data FROM availability WHERE asset_id=?',(aid,)).fetchone()
        result['availability']=json.loads(row[0]) if row else {'state':'not-probed','notice':'Rights eligibility and current provider availability are separate.'}
        return result
    def pack(self,pid):
        row=self.c.db.execute('SELECT * FROM packs WHERE id=? AND kind=\'pack\'',(pid,)).fetchone()
        if not row:raise ValueError('Unknown thematic pack; use library_packs')
        from .catalog import VISIBLE
        counts=dict(self.c.db.execute('SELECT s.section_id,count(*) FROM asset_sections s JOIN assets a ON a.id=s.asset_id LEFT JOIN curation r ON r.asset_id=a.id WHERE s.pack_id=? AND a.active=1 AND '+VISIBLE+' GROUP BY s.section_id',(pid,)))
        return {'id':pid,'name':row['name'],'metadata':json.loads(row['data']),'sections':counts,'records':sum(counts.values()),'view':self.open(pack=pid),'resource_uri':'creativity://pack/'+pid}
    def files(self,aid):
        a=self.require(aid,True)
        cached=self.runtime.db.execute('SELECT revision,data FROM manifests WHERE asset_id=?',(aid,)).fetchone()
        cache_revision='content-v4:'+a['revision']+':'+hashlib.sha256(json.dumps(self.c.details(aid).get('files',[]),sort_keys=True).encode()).hexdigest()
        if cached and cached['revision']==cache_revision: return json.loads(cached['data'])
        d=self.c.details(aid)
        records=d.get('files',[])
        if not records:
            resolved=resolve(self.c,aid)
            records=resolved['links']
            if self.c.source_info(a['source']).get('adapter')=='github-tree' and re.fullmatch('[0-9a-f]{40}',a['revision']):
                records=[{**r,'sha':a['revision'],'role':'main','relative_path':a['upstream_id']} for r in records]
            if a['source']=='ambientcg':
                payload=self.fetch.json(a['access_url'])
                records=[]
                def walk(x,path=()):
                    if isinstance(x,dict):
                        link=x.get('downloadLink') or x.get('downloadUrl')
                        if isinstance(link,str): records.append({'url':link,'filename':x.get('fileName') or x.get('filename') or Path(urlsplit(link).path).name,'bytes':x.get('size') or x.get('sizeBytes'),'variant':'/'.join(path)})
                        for k,v in x.items(): walk(v,path+(k,))
                    elif isinstance(x,list):
                        for i,v in enumerate(x): walk(v,path+(str(i),))
                walk(payload)
                if not records: raise ValueError('Provider did not expose downloadable variants; no web page fallback is used')
        normalized=[]
        for r in records:
            url=r.get('url')
            if not url: continue
            filename=r.get('filename') or Path(urlsplit(url).path).name or 'asset.bin'
            ext=Path(filename).suffix.lower().lstrip('.')
            identity=json.dumps([r.get('sha'),r.get('sha256'),r.get('md5'),r.get('crc32'),r.get('bytes')],separators=(',',':'))
            fid=hashlib.sha256((url+'|'+filename+'|'+r.get('archive_entry','')+'|'+a['revision']+'|'+identity).encode()).hexdigest()[:24]
            normalized.append({**r,'id':fid,'filename':filename,'format':r.get('format') or ext,'mime':MIMES.get(ext) or mimetypes.guess_type(filename)[0] or 'application/octet-stream','resource_uri':f'creativity://asset/{aid}/file/{fid}'})
        result={'asset_id':aid,'license':a['license'],'license_url':a['license_url'],'author':a['author'],'files':normalized,'notice':'Files are fetched internally into a bounded content cache. Prices and unreviewed licenses are never bypassed.'}
        self.runtime.db.execute('INSERT OR REPLACE INTO manifests VALUES (?,?,?)',(aid,cache_revision,json.dumps(result))); self.runtime.db.commit()
        return result
    def file(self,aid,fid='',max_bytes=128*1024*1024):
        if not 1<=max_bytes<=512*1024*1024: raise ValueError('Content budget must be 1..512 MiB')
        a=self.require(aid,True)
        manifest=self.files(aid)
        entries=manifest['files']
        if not entries: raise ValueError('No files available')
        r=next((r for r in entries if r['id']==fid),None) if fid else entries[0]
        if r is None: raise ValueError('File does not belong to this library item')
        source=self.c.source_info(a['source'])
        if r.get('archive_entry'):
            self.safe_member(r['archive_entry'])
            cache_key=hashlib.sha256((r['url']+'|'+r['archive_entry']+'|'+a['revision']).encode()).hexdigest()
            receipt=self.cache.root/(cache_key+'.member.json')
            result=None
            if receipt.exists():
                old=json.loads(receipt.read_text(encoding='utf-8')); p=Path(old['path']).resolve()
                if p.parent==self.cache.root.resolve() and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==old['sha256']: result=old
            if result and result['bytes']>max_bytes: raise ValueError('Archive member exceeds content budget')
            if not result:
                container=self.c.db.execute('SELECT data FROM containers WHERE id=?',(r.get('container_id',''),)).fetchone()
                if r.get('container_id') and not container:raise ValueError('Archive container metadata missing; restore the SQLite snapshot or containers.jsonl.gz')
                archive=self.cache.multipart_zip(json.loads(container[0])['parts']) if container else self.cache.remote_zip(r['url'])
                with archive as z:
                    info=z.getinfo(r['archive_entry']); self.safe_member(info.filename)
                    if info.file_size>max_bytes or info.file_size>max(1,info.compress_size)*500: raise ValueError('Archive member exceeds safe content budget')
                    if r.get('crc32') is not None and info.CRC!=r['crc32']: raise ValueError('Archive member changed; refresh catalog')
                    body=z.read(info)
                result=self.cache.store(body,r['filename'],r['mime'])
                receipt.write_text(json.dumps(result),encoding='utf-8')
        elif r.get('tar_entry'):
            import io,tarfile
            self.safe_member(r['tar_entry'])
            body=self.fetch.read(r['url'],8*1024*1024)
            with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as archive:
                member=archive.getmember(r['tar_entry'])
                if not member.isfile() or member.size>max_bytes:raise ValueError('TAR source member exceeds budget or is not a regular file')
                content=archive.extractfile(member).read(max_bytes+1)
            if len(content)>max_bytes or r.get('sha256') and hashlib.sha256(content).hexdigest()!=r['sha256']:raise ValueError('Current source member integrity mismatch')
            result=self.cache.store(content,r['filename'],r['mime'])
        elif source.get('adapter')=='github-tree' and source.get('repo') and r.get('sha') and re.fullmatch('[0-9a-f]{40}',r['sha']):
            blob=self.fetch.json('https://api.github.com/repos/'+source['repo']+'/git/blobs/'+r['sha'])
            if blob.get('size',0)>max_bytes: raise ValueError('Indexed blob exceeds content budget')
            body=base64.b64decode(blob['content'],validate=False)
            if len(body)>max_bytes: raise ValueError('Decoded blob exceeds content budget')
            result=self.cache.store(body,r['filename'],r['mime'])
        else:
            revision=a['revision'] if a['source'] in {'polyhaven','ambientcg','google-fonts'} or a['source'].startswith(('fuel:','iconify:','quaternius:')) else ''
            result=self.cache.fetch(r['url'],r['filename'],max_bytes,r.get('sha256'),cache_revision=revision)
        path=Path(result['path'])
        if r.get('md5') and hashlib.md5(path.read_bytes()).hexdigest()!=r['md5']: raise ValueError('Provider checksum mismatch')
        with path.open('rb') as f: head=f.read(400)
        ext=Path(r['filename']).suffix.lower()
        if ext!='.html' and head.lstrip().lower().startswith((b'<!doctype html',b'<html')):
            quota=b'quota exceeded' in head.lower()
            info={'state':'provider-quota' if quota else 'provider-access-page','file_id':r['id'],'notice':'Original temporarily unavailable. Provider limits, login and confirmation pages are not bypassed. Try a different indexed variant or another licensed item.','checked_at':__import__('infinite_creativity.catalog',fromlist=['now']).now()}
            self.runtime.db.execute('INSERT OR REPLACE INTO availability VALUES (?,?)',(aid,json.dumps(info)));self.runtime.db.commit()
            alternatives=[x['id'] for x in self.c.search(a['title'].replace('_',' ').split()[0],kind=a['kind'],limit=8,count_total=False)['items'] if x['id']!=aid][:3]
            raise ValueError(('Public provider quota exhausted' if quota else 'Provider returned an HTML/login/confirmation page')+'; access is not bypassed. Use asset_files to select another variant or open_library to select an internal alternative. Alternative item IDs: '+','.join(alternatives))
        if ext=='.wav' and not (head[:4] in {b'RIFF',b'RF64'} and head[8:12]==b'WAVE'):raise ValueError('Original recording is not a valid WAV container')
        if ext=='.zip' and not head.startswith(b'PK'): raise ValueError('Provider returned something other than an asset archive')
        if ext=='.glb' and not head.startswith(b'glTF'): raise ValueError('Provider returned something other than a GLB model')
        if head.startswith(b'version https://git-lfs.github.com/spec/v1'):
            text=head.decode('ascii'); oid=re.search(r'oid sha256:([0-9a-f]{64})',text); size=re.search(r'size (\d+)',text)
            if not oid or not size or int(size[1])>max_bytes: raise ValueError('Git LFS content exceeds budget or has an invalid pointer')
            p=urlsplit(r['url'])
            if p.hostname!='raw.githubusercontent.com': raise ValueError('Unsupported LFS origin')
            result=self.cache.fetch('https://media.githubusercontent.com/media'+p.path,r['filename'],max_bytes,oid[1],cache_revision=oid[1]); path=Path(result['path'])
        elif r.get('sha') and re.fullmatch('[0-9a-f]{40}',r['sha']):
            body=path.read_bytes()
            if hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()!=r['sha']:
                raise ValueError('Upstream file differs from indexed revision; refresh catalog before using it')
        if r.get('transport')=='gzip':
            import gzip
            with gzip.open(path,'rb') as compressed:body=compressed.read(max_bytes+1)
            if len(body)>max_bytes or len(body)>max(1,result['bytes'])*500:raise ValueError('Compressed original exceeds safe expanded content budget')
            result=self.cache.store(body,r['filename'],r['mime']);path=Path(result['path'])
        if Path(r['filename']).suffix.lstrip('.').lower() in TEXT_FORMATS:
            if getattr(self,'live_policy',False) and __import__('os').environ.get('IC_SAFETY_MODE','strict')=='strict':
                from .policy import review_terms
                text=path.read_text(encoding='utf-8-sig',errors='replace')
                if not acceptable(text) or review_terms(text):raise ValueError('Original text withheld by live explicit/suggestive content policy')
            with path.open('rb') as f: header=f.read(4000).decode('utf-8',errors='replace')
            declared=re.search(r'SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)',header)
            if declared and declared[1]!=a['license']: raise ValueError('File license declaration conflicts with indexed license; review required')
        if getattr(self,'live_review',None):self.live_review(r,path)
        self.runtime.db.execute('INSERT OR REPLACE INTO availability VALUES (?,?)',(aid,json.dumps({'state':'verified-file','file_id':r['id'],'filename':r['filename'],'checked_at':__import__('infinite_creativity.catalog',fromlist=['now']).now(),'notice':'This selected file was retrieved; other variants and future provider availability are separate.'})));self.runtime.db.commit()
        return {**result,'asset_id':aid,'file_id':r['id'],'resource_uri':r['resource_uri'],'relative_path':r.get('relative_path',r['filename']),'mime':r['mime'],'license':a['license'],'license_url':a['license_url'],'author':a['author'],'component_legal':self.c.details(aid).get('legal',[])}
    def code(self,aid,fid='',start_line=1,line_count=200):
        if not 1<=start_line or not 1<=line_count<=400: raise ValueError('Invalid code window')
        r=self.file(aid,fid,2*1024*1024)
        if Path(r['filename']).suffix.lower().lstrip('.') not in TEXT_FORMATS: raise ValueError('Use read_asset_file for binary content')
        text=Path(r['path']).read_text(encoding='utf-8-sig')
        lines=text.splitlines(); window='\n'.join(lines[start_line-1:start_line-1+line_count])[:40000]
        imports=sorted(set(re.findall(r'(?:from\s+|import\s+)[\"\']([^\"\']+)[\"\']',text)))
        return {**r,'text':window,'start_line':start_line,'total_lines':len(lines),'next_line':start_line+line_count if start_line+line_count<=len(lines) else None,'dependencies':imports,'notice':'Untrusted source code; returned for inspection, never executed.'}
    def chunk(self,aid,fid,offset=0,length=65536):
        if offset<0 or not 1<=length<=1024*1024: raise ValueError('Invalid byte window')
        r=self.file(aid,fid,512*1024*1024)
        with Path(r['path']).open('rb') as f: f.seek(offset); body=f.read(length)
        return {**r,'offset':offset,'encoding':'base64','data':base64.b64encode(body).decode(),'next_offset':offset+len(body) if offset+len(body)<r['bytes'] else None}
    def dependency(self,aid,specifier):
        a=self.require(aid,True); s=self.c.source_info(a['source'])
        if s.get('adapter')!='github-tree' or not s.get('repo'): raise ValueError('Dependency browsing is limited to verified component repositories')
        code=self.code(aid)
        if specifier not in code['dependencies']: raise ValueError('Requested dependency is not declared by this source file')
        if not specifier.startswith(('./','../','@/','~/')): return {'type':'package','name':specifier,'notice':'Package dependency; its own license/version must be checked separately.'}
        repo=s['repo']; meta=self.fetch.json('https://api.github.com/repos/'+repo)
        branch=meta['default_branch']; tree=self.fetch.json(f'https://api.github.com/repos/{repo}/git/trees/{quote(branch,safe="")}?recursive=1')
        if tree.get('truncated'): raise ValueError('Dependency tree is incomplete')
        entries={e['path']:e for e in tree.get('tree',[]) if e['type']=='blob'}
        primary=a['upstream_id']
        if entries.get(primary,{}).get('sha')!=a['revision']: raise ValueError('Component changed upstream; refresh before resolving coherent dependencies')
        if specifier.startswith(('./','../')): target=posixpath.normpath(posixpath.join(posixpath.dirname(primary),specifier))
        else:
            parents=[str(p) for p in Path(primary).parents]
            project=next((p.replace('\\','/') for p in parents if (p.replace('\\','/').rstrip('.')+'/package.json').lstrip('/') in entries),'')
            target=posixpath.join(project if project!='.' else '',specifier[2:])
        if target.startswith('../') or target.startswith('/'): raise ValueError('Dependency escapes its repository')
        allowed=('.ts','.tsx','.js','.jsx','.css','.json','.vue','.svelte','.glsl')
        candidates=[target]+[target+ext for ext in allowed]+[target+'/index'+ext for ext in allowed]
        matched=next((p for p in candidates if p in entries and Path(p).suffix in allowed),None)
        if not matched: raise ValueError('Declared dependency has no verified source-file match')
        e=entries[matched]; url=f'https://raw.githubusercontent.com/{repo}/{quote(branch)}/{quote(matched,safe="/")}'
        manifest=self.files(aid); filename=Path(matched).name
        fid=hashlib.sha256((url+'|'+filename).encode()).hexdigest()[:24]
        if not any(f['id']==fid for f in manifest['files']):
            manifest['files'].append({'id':fid,'url':url,'filename':filename,'relative_path':matched,'sha':e['sha'],'bytes':e.get('size'),'format':Path(matched).suffix.lstrip('.'),'mime':'text/plain','role':'dependency','resource_uri':f'creativity://asset/{aid}/file/{fid}'})
            self.runtime.db.execute('UPDATE manifests SET data=? WHERE asset_id=?',(json.dumps(manifest),aid)); self.runtime.db.commit()
        return self.code(aid,fid)
    def archive_entry(self,aid,fid,entry,offset=0,length=65536):
        if offset<0 or not 1<=length<=1024*1024: raise ValueError('Invalid archive byte window')
        r=self.file(aid,fid,512*1024*1024)
        if not r['filename'].lower().endswith('.zip'): raise ValueError('Not a ZIP asset bundle')
        self.safe_member(entry)
        with zipfile.ZipFile(r['path']) as z:
            info=z.getinfo(entry)
            if info.is_dir() or info.file_size>128*1024*1024 or info.file_size>max(1,info.compress_size)*500: raise ValueError('Archive member exceeds safe read budget')
            with z.open(info) as f: f.seek(offset); body=f.read(length)
        return {'asset_id':aid,'file_id':fid,'entry':entry,'entry_bytes':info.file_size,'offset':offset,'encoding':'base64','data':base64.b64encode(body).decode(),'next_offset':offset+len(body) if offset+len(body)<info.file_size else None,'license':r['license']}
    @staticmethod
    def safe_member(entry):
        parts=entry.replace('\\','/').split('/')
        if '..' in parts or entry.startswith(('/','\\')) or re.match(r'^[A-Za-z]:',entry): raise ValueError('Unsafe archive member path')
    def preview(self,aid):
        a=self.require(aid); d=self.c.details(aid)
        study=d.get('reference_preview') if not a['usable'] else None
        if not a['usable'] and not study:raise ValueError('Reference has no permitted public presentation preview')
        previews=d.get('previews',[])
        if previews: url=previews[0].get('url') if isinstance(previews[0],dict) else previews[0]
        elif a['source']=='polyhaven': url='https://cdn.polyhaven.com/asset_img/thumbs/'+quote(a['upstream_id'])+'.png?width=512&height=512'
        elif a['source']=='ambientcg': url='https://ambientcg.com/get?file='+quote(a['upstream_id'])+'_preview.jpg'
        elif a['kind'] in {'texture','sprite','illustration','image','icon'}:
            r=self.file(aid,max_bytes=10*1024*1024)
            if r['mime']=='image/svg+xml': return {**r,'svg':Path(r['path']).read_text(encoding='utf-8')}
            return r
        elif getattr(self,'live_policy',False) and a['kind'] in {'model-3d','animation-3d','scene-3d'}:
            file=next((f for f in self.files(aid)['files'] if f['format']=='glb'),None)
            if not file:raise ValueError('Original model has no locally renderable GLB variant')
            original=self.file(aid,file['id'],32*1024*1024)
            from .live_media_review import render_glb_preview
            result=self.cache.store(render_glb_preview(Path(original['path']).read_bytes()),'model-preview.png','image/png')
            return {**result,'asset_id':aid,'license':a['license'],'credit':a['author'],'preview_only':True,'preview_notice':'Local isometric view of current reviewed geometry; material face colours, not a photorealistic render.'}
        else: raise ValueError('No licensed preview is indexed for this item; inspect its files or 3D data inside MCP')
        result=self.cache.fetch(url,'preview'+(Path(urlsplit(url).path).suffix or '.png'),2*1024*1024 if study else 10*1024*1024,cache_revision=a['revision'])
        with Path(result['path']).open('rb') as f: header=f.read(16)
        result['mime']='image/png' if header.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if header.startswith(b'\xff\xd8\xff') else 'image/webp' if header.startswith(b'RIFF') and header[8:12]==b'WEBP' else result['mime']
        return {**result,'asset_id':aid,'license':a['license'],'credit':a['author'],'preview_only':bool(study),'preview_notice':study.get('notice') if study else 'Original asset license applies.'}
    def inspect_3d(self,aid,fid=''):
        r=self.file(aid,fid,64*1024*1024)
        ext=Path(r['filename']).suffix.lower()
        if ext=='.glb':
            with Path(r['path']).open('rb') as f:
                magic,version,size=struct.unpack('<4sII',f.read(12))
                if magic!=b'glTF' or version!=2: raise ValueError('Unsupported GLB header')
                length,kind=struct.unpack('<II',f.read(8))
                if kind!=0x4E4F534A or length>16*1024*1024: raise ValueError('Invalid or oversized GLB JSON chunk')
                doc=json.loads(f.read(length))
        elif ext=='.gltf': doc=json.loads(Path(r['path']).read_text(encoding='utf-8'))
        elif ext=='.zip':
            with zipfile.ZipFile(r['path']) as z:
                entries=[{'path':i.filename,'bytes':i.file_size,'compressed_bytes':i.compress_size} for i in z.infolist() if not i.is_dir()]
            return {**r,'archive_files':entries[:500],'total_files':len(entries),'formats':sorted({Path(e['path']).suffix.lstrip('.').lower() for e in entries}),'notice':'Archive inventory only; use read_archive_entry for internal file content. No extraction or code execution.'}
        else: return {**r,'format':ext,'inspection':'Original file available; native Blender/FBX/USD inspection requires a separately installed parser.'}
        triangles=0
        for mesh in doc.get('meshes',[]):
            for p in mesh.get('primitives',[]):
                if p.get('mode',4)==4 and 'indices' in p: triangles+=doc.get('accessors',[])[p['indices']].get('count',0)//3
        return {**r,'meshes':len(doc.get('meshes',[])),'materials':len(doc.get('materials',[])),'nodes':len(doc.get('nodes',[])),'skins':len(doc.get('skins',[])),'animation_clips':[a.get('name',f'clip-{i}') for i,a in enumerate(doc.get('animations',[]))],'indexed_triangles':triangles,'images':len(doc.get('images',[])),'extensions':doc.get('extensionsUsed',[]),'external_dependencies':[x.get('uri') for group in ('buffers','images') for x in doc.get(group,[]) if x.get('uri') and not x['uri'].startswith('data:')]}
    def inspect_media(self,aid,fid=''):
        r=self.file(aid,fid,32*1024*1024);path=Path(r['path']);ext=Path(r['filename']).suffix.lower()
        if ext=='.wav':
            import wave
            try:
                with wave.open(str(path),'rb') as w:info={'channels':w.getnchannels(),'sample_rate':w.getframerate(),'sample_width_bytes':w.getsampwidth(),'frames':w.getnframes(),'duration_seconds':w.getnframes()/w.getframerate(),'compression':w.getcomptype()}
            except wave.Error:return {**r,'inspection':'Valid RIFF/RF64 signature; this WAV encoding needs a separately installed codec parser.'}
            return {**r,'audio':info,'safety_scope':'Container metadata only; speech and sound meaning have not been reviewed by this inspection.'}
        with path.open('rb') as f:header=f.read(128)
        if ext in {'.aseprite','.ase'}:
            if len(header)<128 or struct.unpack_from('<H',header,4)[0]!=0xA5E0:raise ValueError('Invalid Aseprite header')
            frames,width,height,depth=struct.unpack_from('<4H',header,6)
            return {**r,'animation':{'frames':frames,'width':width,'height':height,'color_depth':depth},'inspection':'Original Aseprite animation header; frame pixels are not automatically visually certified.'}
        if header.startswith(b'\x89PNG\r\n\x1a\n') and len(header)>=24:
            width,height=struct.unpack_from('>II',header,16);return {**r,'image':{'width':width,'height':height},'inspection':'Original raster container dimensions; see separate curation evidence for image review.'}
        if ext in {'.cube','.3dl','.look','.clf'}:
            text=path.read_text(encoding='utf-8-sig',errors='replace');grid=re.search(r'^LUT_3D_SIZE\s+(\d+)',text,re.M)
            values=[line for line in text.splitlines() if re.fullmatch(r'\s*[-+0-9.eE]+\s+[-+0-9.eE]+\s+[-+0-9.eE]+\s*',line)]
            return {**r,'lut':{'grid_size':int(grid[1]) if grid else None,'numeric_rows':len(values),'expected_3d_rows':int(grid[1])**3 if grid else None,'color_management':self.c.details(aid).get('features',{})},'inspection':'Numeric structure only; LUT quality depends on declared input/output encoding and representative footage.'}
        return {**r,'inspection':'Original format available inside MCP; this format requires a separately installed specialized metadata parser.'}
    def bundle(self,aid,file_ids=None,max_total_bytes=256*1024*1024):
        if not 1<=max_total_bytes<=512*1024*1024: raise ValueError('Bundle budget must be 1..512 MiB')
        manifest=self.files(aid); selected=manifest['files']
        if file_ids is None:
            if selected and selected[0].get('bundle_key'):
                key=selected[0]['bundle_key']; selected=[f for f in selected if f.get('bundle_key')==key or f.get('role')=='license']
            else:
                role_files=[f for f in selected if f.get('role') in {'main','dependency','license','provenance'}]
                selected=role_files or selected[:1]
        else:
            unknown=set(file_ids)-{f['id'] for f in selected}
            if unknown: raise ValueError('Unknown bundle file')
            keys={f['bundle_key'] for f in selected if f['id'] in file_ids and f.get('bundle_key') and f.get('role')!='dependency'}
            selected=[f for f in selected if f['id'] in file_ids or (f.get('bundle_key') in keys and f.get('role')=='dependency')]
        if len(selected)>100: raise ValueError('Select at most 100 bundle files')
        fetched=[]; total=0
        for f in selected:
            if total>=max_total_bytes: raise ValueError('Bundle exceeds total byte budget')
            r=self.file(aid,f['id'],max_total_bytes-total); fetched.append(r); total+=r['bytes']
        return {'asset_id':aid,'files':fetched,'total_bytes':total,'license':manifest['license'],'license_url':manifest['license_url'],'author':manifest['author'],'component_legal':self.c.details(aid).get('legal',[]),'notice':'All component license notices apply. Files stay in the cache; copy original filenames when assembling a project. Never execute retrieved code automatically.'}
