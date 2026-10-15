"""Live, rights-scoped upstream collections. No local catalogue is produced."""
import hashlib,json,re
from pathlib import PurePosixPath
from urllib.parse import quote,urlsplit
from .policy import acceptable,review_terms
from .asset_adapters import MEDIA,complete_tree

def safe_path(value):
    if not isinstance(value,str) or not value or len(value)>1024 or value.startswith('/') or '\\' in value or ':' in value or any(p in {'.','..'} for p in value.split('/')):raise ValueError('Invalid upstream collection path')
    return value

def current(http,s):
    repo=s['repo'];meta=http.json('https://api.github.com/repos/'+repo)
    if meta.get('private'):raise ValueError('Collection is no longer public')
    commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+quote(meta['default_branch'],safe=''))['sha']
    return repo,commit,'https://raw.githubusercontent.com/'+repo+'/'+commit+'/'

def descriptor_catalog(http,s,f,after,limit,key=None):
    from .live_providers import item,window
    from .live_catalogs import cc_license
    repo,commit,raw=current(http,s);data=http.json(raw+'catalog.json')
    if not isinstance(data,list) or len(data)>50000:raise ValueError('Unexpected original descriptor catalogue shape/budget')
    rows=[]
    for d in data:
        if not isinstance(d,dict) or d.get('schemaVersion')!=1 or not isinstance(d.get('id'),str) or key is not None and d['id']!=key:continue
        if f.get('_pack_key') and d.get('collection')!=f['_pack_key']:continue
        lic,uri=cc_license(d.get('licenseUrl',''))
        if lic not in {'CC0-1.0','CC-BY-4.0'} or d.get('license')!=lic:continue
        path=safe_path(d.get('file'));digest=d.get('sha256','');size=d.get('bytes')
        if not re.fullmatch('[a-f0-9]{64}',digest) or not isinstance(size,int) or size<=0:continue
        ext=PurePosixPath(path).suffix.lstrip('.').lower()
        if ext not in MEDIA:continue
        creator=d.get('creator',{});author=creator.get('name','') if isinstance(creator,dict) else str(creator)
        if lic=='CC-BY-4.0' and (not author or not d.get('attribution')):continue
        kind={'model':'model-3d','animation':'animation-3d','rig':'pose-3d','image':'illustration'}.get(d.get('kind'),MEDIA[ext])
        previews=[]
        if isinstance(d.get('preview'),str) and d['preview']:previews=[{'url':raw+quote(safe_path(d['preview']),safe='/')}]
        files=[{'url':raw+quote(path,safe='/'),'filename':PurePosixPath(path).name,'relative_path':path,'sha256':digest,'bytes':size,'role':'main'}]
        a=item(s['id'],d['id'],d.get('name',PurePosixPath(path).stem),kind,lic,uri,author,d.get('tags',[]),[ext],files,previews,d.get('description',''),d.get('collection',''),commit)
        a['features']={'declared_technical':d.get('technical',{}),'declared_usage':d.get('usage',{}),'provenance':d.get('source',{}),'attribution':d.get('attribution',''),'evidence_scope':'Current publisher descriptor; technical/compatibility assertions are not independent measurements.'}
        a['origin_url']='https://github.com/'+repo+'/blob/'+commit+'/'+quote(path,safe='/')
        rows.append(a)
    if key is not None:
        if not rows:raise ValueError('Descriptor removed, unsupported or no longer licensed')
        return rows[0]
    return window(rows,after,limit,f)

def pack_library(http,s,f,after,limit,key=None):
    """Traverse one selected subtree, never request a giant recursive root tree."""
    from .live_providers import item,window,github
    repo,commit,raw=current(http,s)
    direct=http.json('https://api.github.com/repos/'+repo+'/git/trees/'+commit)
    if direct.get('truncated'):raise ValueError('Collection root directory is incomplete')
    roots={e['path']:e for e in direct.get('tree',[]) if e['type']=='tree' and not e['path'].startswith(('.','scripts','node_modules'))}
    requested_scope=f.get('_pack_key','');pack=requested_scope.split('/',1)[0] if requested_scope else (key.split('/',1)[0] if key else '')
    def folder(name):
        a=item(s['id'],name,name.replace('-',' ').replace('_',' '),'asset-pack',author=repo.split('/')[0],tags=[name,'curated-pack'],pack=name,revision=commit)
        a.update(navigation_only=True,member_kind='collection-folder')
        a['features']={'rights':'Navigation only. Every selected member needs its own current pack dedication; RUN/platform-restricted licences are excluded.'}
        return a
    if not pack:
        if any(f.get(k) for k in ('query','kind','format','section')) and not f.get('section','').startswith('discovery'):
            words=f.get('query','').lower().split();names=sorted((n for n in roots if acceptable(n) and not review_terms(n)),key=lambda n:(not any(w in n.lower() for w in words),n))
            state=json.loads(after) if after else {'pack':names[0] if names else '', 'member':''}
            if not names:return {'items':[],'next':None,'scope':'No policy-eligible pack directories in the current root'}
            if state['pack'] not in names:raise ValueError('Pack directory changed; open a fresh live view')
            index=names.index(state['pack']);rows=[];errors=[];member=state['member'];scanned=0;next_cursor=None
            while index<len(names) and scanned<2:
                name=names[index]
                try:
                    result=pack_library(http,s,{**f,'_pack_key':name},member,limit-len(rows))
                    rows+=result['items']
                    if result.get('next'):
                        next_cursor=json.dumps({'pack':name,'member':result['next']});break
                except ValueError as e:errors.append({'pack':name,'reason':str(e)[:180]})
                index+=1;scanned+=1;member=''
                if len(rows)>=limit:break
            if not next_cursor and index<len(names):next_cursor=json.dumps({'pack':names[index],'member':''})
            return {'items':rows,'next':next_cursor,'scope':'Fresh licensed pack subtrees; bounded two-pack traversal. Continue even after an empty window.','repository_errors':errors}
        if f.get('mode')=='reference':return {'items':[],'next':None,'scope':'Collection navigation is not a paid visual reference'}
        return window([folder(name) for name in roots if acceptable(name) and not review_terms(name)],after,limit,{**f,'mode':'all'})
    if pack not in roots:raise ValueError('Pack no longer exists in this public collection')
    if key==pack:return folder(pack)
    scoped=complete_tree(http,repo,roots[pack]['sha'],max_requests=16)
    entries=[{**e,'path':pack+'/'+e['path']} for e in scoped if e['type']=='blob']
    # A platform-only outer licence must not be overridden by a copied nested
    # CC0 notice. Inspect all licence files in this selected pack first.
    notices=[e for e in entries if PurePosixPath(e['path']).name.lower() in {'license','license.txt','license.md','copying','cc0.txt'}]
    if not notices or len(notices)>16:raise ValueError('Selected pack has no bounded complete licence scope')
    for notice in notices:
        text=http.text(raw+quote(notice['path'],safe='/'),256*1024).lower()
        if any(t in text for t in ('run repository supplemental license','run projects only','run.studio projects only','personal use only','non-commercial','noncommercial')):raise ValueError('Selected pack has restricted/platform-only rights; originals excluded')
    class ScopedHTTP:
        def __getattr__(self,name):return getattr(http,name)
        def json(self,url):
            if url=='https://api.github.com/repos/'+repo+'/git/trees/'+commit+'?recursive=1':return {'tree':entries,'truncated':False}
            return http.json(url)
    narrowed={**s,'adapter':'github-assets','media_license_scope':'pack-license','path_pattern':'.*'}
    return github(ScopedHTTP(),narrowed,{**f,'_pack_key':requested_scope or pack},after,limit,key)

def open_asset_archive(http,s,f,after,limit,key=None):
    """A public mirror is usable only after current first-party pack rights."""
    from .live_providers import item,window
    repo,commit,raw=current(http,s);records=http.json(raw+'all-assets.json');packs=http.json(raw+'packs.json')
    if not isinstance(records,list) or len(records)>50000 or not isinstance(packs,list):raise ValueError('Unexpected live archive catalogue shape')
    by_pack={p['id']:p for p in packs if isinstance(p,dict) and p.get('id')};rights={};rows=[];tree=None
    # Filter before original metadata/rights requests, keeping narrow queries
    # within the public source budget. Never turn a mirror's licence label into
    # authority for an unknown creator or platform-only library.
    from .live_providers import matches
    for d in sorted(records,key=lambda d:d.get('id','')):
        if not d.get('id') or key is not None and d['id']!=key or key is None and d['id']<=after:continue
        if f.get('_pack_key') and d.get('packId')!=f['_pack_key']:continue
        p=by_pack.get(d.get('packId'),{});origin=p.get('sourceUrl','');host=(urlsplit(origin).hostname or '').lower()
        if d.get('license') not in {'CC0','CC0-1.0'} or p.get('license') not in {'CC0','CC0-1.0'} or host not in {'kenney.nl','quaternius.com','www.quaternius.com'}:continue
        if not ((host=='kenney.nl' and re.fullmatch('/assets/[a-z0-9-]+',urlsplit(origin).path)) or ('quaternius.com' in host and re.fullmatch('/packs/[A-Za-z0-9_-]+\.html',urlsplit(origin).path))):continue
        path=safe_path(d.get('publicPath'));ext=PurePosixPath(path).suffix.lstrip('.').lower()
        if ext not in MEDIA or d.get('errorCount',0):continue
        a=item(s['id'],d['id'],d.get('name',d['id']),MEDIA[ext],'CC0-1.0',origin,p.get('creator',''),d.get('tags',[]),[ext],description=d.get('description',''),pack=d.get('packId',''),revision=commit)
        if not matches(a,f):continue
        if origin not in rights:
            http.approve_content(origin);body=http.text(origin)
            rights[origin]=bool(re.search(r'creativecommons\.org/publicdomain/zero/1\.0|\bCC0\b',body,re.I))
        if not rights[origin]:continue
        if tree is None:tree={e['path']:e for e in complete_tree(http,repo,commit,max_requests=16) if e['type']=='blob'}
        original=tree.get(path)
        if not original:continue
        base=str(PurePosixPath(path).parent)
        dependencies=[e for e in tree.values() if e['path']!=path and e['path'].startswith(base+'/') and PurePosixPath(e['path']).suffix.lower() in {'.bin','.png','.jpg','.jpeg','.webp','.ktx2'}]
        if len(dependencies)>32:continue
        a['files']=[{'url':raw+quote(e['path'],safe='/'),'filename':PurePosixPath(e['path']).name,'relative_path':e['path'],'sha':e['sha'],'bytes':e.get('size'),'role':'main' if e==original else 'dependency'} for e in [original]+dependencies]
        preview=d.get('preview',{})
        if isinstance(preview,dict) and preview.get('relativePath') in tree:a['previews']=[{'url':raw+quote(preview['relativePath'],safe='/')}]
        a['features']={'declared_technical':{k:d[k] for k in ('triangleCount','materialCount','textureCount','rigged','animationCount','jointCountTotal','dependencyMode','bounds') if k in d},'origin_rights_verified_at_request':True,'evidence_scope':'Mirror technical claims; current first-party CC0 pack page plus pinned repository file identities.'}
        # Cross-provider mirrors of the same source/filename are suppressed by
        # Admission's origin identity in addition to exact original hashes.
        name=PurePosixPath(path).stem.lower().removeprefix(d.get('packId','')+'-')
        a['origin_url']=origin+'#'+name
        a['origin_identity']=origin+'|'+re.sub('[^a-z0-9]+','-',name).strip('-')
        rows.append(a)
        if key is None and len(rows)>limit:break
    if key is not None:
        if not rows:raise ValueError('Original missing, restricted or no longer first-party rights eligible')
        return rows[0]
    return window(rows,after,limit,f)
