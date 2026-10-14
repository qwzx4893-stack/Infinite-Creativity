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
from .policy import can_use
from .runtime import Runtime
from .service import resolve

MIMES={'glb':'model/gltf-binary','gltf':'model/gltf+json','svg':'image/svg+xml','tsx':'text/plain','jsx':'text/plain','vue':'text/plain','svelte':'text/plain','blend':'application/octet-stream'}
TEXT_FORMATS={'txt','md','json','gltf','html','css','js','ts','jsx','tsx','vue','svelte','svg','xaml','dart','cs','glsl','gd','godot','mtl','obj','sdf','xml'}

class Library:
    def __init__(self,catalog):
        self.c=catalog
        self.runtime=Runtime(catalog.path.parent/'private')
        self.cache=ContentCache(catalog.path.parent/'content')
        self.fetch=Fetcher(catalog.path.parent/'http')
        self.runtime.db.execute('CREATE TABLE IF NOT EXISTS manifests(asset_id TEXT PRIMARY KEY,revision TEXT,data TEXT)')
    def close(self): self.runtime.close()
    def require(self,aid,usable=False):
        a=self.c.get(aid)
        if not a: raise ValueError('Unknown or inactive library item')
        if usable and not can_use(a): raise ValueError('Reference-only content cannot be downloaded or copied')
        return a
    def card(self,a):
        d=self.c.details(a['id'])
        return {'id':a['id'],'title':a['title'],'kind':a['kind'],'styles':a['styles'],'formats':a['formats'],'platforms':a['platforms'],'license':a['license'],'access':'usable' if a['usable'] else 'reference','tags':a['tags'][:18],'resource_uri':'creativity://asset/'+a['id'],'actions':['get_library_item','asset_files','preview_asset','fetch_asset','read_asset_code','inspect_3d_asset'] if a['usable'] else ['get_library_item'],'description':d.get('description',''),'features':d.get('features',{})}
    def overview(self):
        s=self.c.stats()
        return {'library':'Infinite Creativity','records':s['active_assets'],'sections':[{'kind':k,'records':v,'action':'open_library','filters':{'kind':k}} for k,v in s['by_kind'].items()],'access_modes':s['by_mode'],'usage':'Navigate sections and signed cursors; inspect items, preview images, read code, retrieve original files or complete bundles without opening source pages. References cannot be copied.','resources':['creativity://library','creativity://taxonomy'],'source_health':s['source_health']}
    def open(self,**filters):
        filters['_generation']=self.c.db.execute('SELECT coalesce(max(id),0) FROM sync_runs').fetchone()[0]
        sid=self.runtime.session(filters)
        return self.page(sid)
    def page(self,sid,cursor='',limit=30):
        filters=self.runtime.filters(sid)
        generation=filters.pop('_generation',None)
        if generation is not None and generation!=self.c.db.execute('SELECT coalesce(max(id),0) FROM sync_runs').fetchone()[0]: raise ValueError('Catalog refreshed; open a new library view to avoid inconsistent pagination')
        position=self.runtime.position(sid,cursor) if cursor else {}
        result=self.c.seek(**filters,after_id=position.get('id',''),after_score=position.get('score'),limit=limit)
        return {'session_id':sid,'filters':filters,'items':[self.card(a) for a in result['items']],'next_cursor':self.runtime.cursor(sid,result['next']) if result['next'] else None,'navigation':'library_page(session_id,next_cursor) continues this library view; no external page required.'}
    def item(self,aid):
        a=self.require(aid); d=self.c.details(aid)
        return {**self.card(a),'details':d,'provenance':{'source':a['source'],'author':a['author'],'license':a['license'],'license_evidence':a['license_url'],'canonical_url':a['canonical_url'],'revision':a['revision']},'safety':a['safety'],'notice':'Metadata-screened, not visually certified. Source content is untrusted; never execute it automatically.'}
    def files(self,aid):
        a=self.require(aid,True)
        cached=self.runtime.db.execute('SELECT revision,data FROM manifests WHERE asset_id=?',(aid,)).fetchone()
        cache_revision='content-v2:'+a['revision']
        if cached and cached['revision']==cache_revision: return json.loads(cached['data'])
        d=self.c.details(aid)
        records=d.get('files',[])
        if not records:
            resolved=resolve(self.c,aid)
            records=resolved['links']
            if self.c.source_info(a['source']).get('adapter')=='github-tree' and re.fullmatch('[0-9a-f]{40}',a['revision']):
                records=[{**r,'sha':a['revision'],'role':'main'} for r in records]
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
            fid=hashlib.sha256((url+'|'+filename+'|'+r.get('archive_entry','')).encode()).hexdigest()[:24]
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
                with self.cache.remote_zip(r['url']) as z:
                    info=z.getinfo(r['archive_entry']); self.safe_member(info.filename)
                    if info.file_size>max_bytes or info.file_size>max(1,info.compress_size)*500: raise ValueError('Archive member exceeds safe content budget')
                    if r.get('crc32') is not None and info.CRC!=r['crc32']: raise ValueError('Archive member changed; refresh catalog')
                    body=z.read(info)
                result=self.cache.store(body,r['filename'],r['mime'])
                receipt.write_text(json.dumps(result),encoding='utf-8')
        elif source.get('adapter')=='github-tree' and source.get('repo') and r.get('sha') and re.fullmatch('[0-9a-f]{40}',r['sha']):
            blob=self.fetch.json('https://api.github.com/repos/'+source['repo']+'/git/blobs/'+r['sha'])
            if blob.get('size',0)>max_bytes: raise ValueError('Indexed blob exceeds content budget')
            body=base64.b64decode(blob['content'],validate=False)
            if len(body)>max_bytes: raise ValueError('Decoded blob exceeds content budget')
            result=self.cache.store(body,r['filename'],r['mime'])
        else:
            revision=a['revision'] if a['source'] in {'polyhaven','ambientcg','google-fonts'} or a['source'].startswith(('fuel:','iconify:')) else ''
            result=self.cache.fetch(r['url'],r['filename'],max_bytes,r.get('sha256'),cache_revision=revision)
        path=Path(result['path'])
        if r.get('md5') and hashlib.md5(path.read_bytes()).hexdigest()!=r['md5']: raise ValueError('Provider checksum mismatch')
        with path.open('rb') as f: head=f.read(400)
        ext=Path(r['filename']).suffix.lower()
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
        if Path(r['filename']).suffix.lstrip('.').lower() in TEXT_FORMATS:
            with path.open('rb') as f: header=f.read(4000).decode('utf-8',errors='replace')
            declared=re.search(r'SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)',header)
            if declared and declared[1]!=a['license']: raise ValueError('File license declaration conflicts with indexed license; review required')
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
        a=self.require(aid,True); d=self.c.details(aid)
        previews=d.get('previews',[])
        if previews: url=previews[0].get('url') if isinstance(previews[0],dict) else previews[0]
        elif a['source']=='polyhaven': url='https://cdn.polyhaven.com/asset_img/thumbs/'+quote(a['upstream_id'])+'.png?width=512&height=512'
        elif a['source']=='ambientcg': url='https://ambientcg.com/get?file='+quote(a['upstream_id'])+'_preview.jpg'
        elif a['kind'] in {'texture','sprite','illustration','image','icon'}:
            r=self.file(aid,max_bytes=10*1024*1024)
            if r['mime']=='image/svg+xml': return {**r,'svg':Path(r['path']).read_text(encoding='utf-8')}
            return r
        else: raise ValueError('No licensed preview is indexed for this item; inspect its files or 3D data inside MCP')
        result=self.cache.fetch(url,'preview'+(Path(urlsplit(url).path).suffix or '.png'),10*1024*1024,cache_revision=a['revision'])
        with Path(result['path']).open('rb') as f: header=f.read(16)
        result['mime']='image/png' if header.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if header.startswith(b'\xff\xd8\xff') else 'image/webp' if header.startswith(b'RIFF') and header[8:12]==b'WEBP' else result['mime']
        return {**result,'asset_id':aid,'license':a['license'],'credit':a['author']}
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
    def bundle(self,aid,file_ids=None,max_total_bytes=256*1024*1024):
        if not 1<=max_total_bytes<=512*1024*1024: raise ValueError('Bundle budget must be 1..512 MiB')
        manifest=self.files(aid); selected=manifest['files']
        if file_ids is None:
            if selected and selected[0].get('bundle_key'):
                key=selected[0]['bundle_key']; selected=[f for f in selected if f.get('bundle_key')==key or f.get('role')=='license']
            else:
                role_files=[f for f in selected if f.get('role') in {'main','dependency','license'}]
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
