"""Item-level licensed 3D/2D/audio repositories and public model archives."""
import hashlib
import re
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import quote
from .content import ContentCache
from .policy import LICENSES,acceptable

MEDIA={'glb':'model-3d','gltf':'model-3d','blend':'model-3d','fbx':'model-3d','obj':'model-3d','usd':'scene-3d','usdz':'scene-3d','vdb':'volume-3d','abc':'animation-3d','png':'texture','jpg':'texture','jpeg':'texture','webp':'texture','svg':'illustration','exr':'texture','hdr':'hdri','wav':'audio','ogg':'audio','mp3':'audio','flac':'audio','ttf':'font','otf':'font'}
MEDIA.update({'woff':'font','woff2':'font','capx':'template','c3p':'template','unitypackage':'template','aseprite':'sprite','ase':'sprite'})
MEDIA.update({'cube':'lut','3dl':'lut','look':'lut','glsl':'shader','frag':'shader','vert':'shader','riv':'vector-animation','sif':'animation-2d','kra':'illustration','ora':'illustration','kdenlive':'editing-template','mlt':'editing-template','aep':'editing-template','drp':'editing-template','prproj':'editing-template','mp4':'video','webm':'video','mov':'video','gif':'animation-2d'})
FORMAT_DIRS={'glb','gltf','fbx','obj','blend','models','meshes','formats','gltf format','glb format','fbx format','obj format','blend format'}

def complete_tree(fetch,repo,commit,max_requests=2500):
    result=[];queue=[(commit,'')];requests=0
    while queue:
        sha,prefix=queue.pop();requests+=1
        if requests>max_requests:raise ValueError('Complete tree request budget exceeded')
        tree=fetch.json(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1')
        if not tree.get('truncated'):
            result.extend({**e,'path':prefix+e['path']} for e in tree.get('tree',[]))
            if len(result)>350000:raise ValueError('Tree entry budget exceeded')
            continue
        direct=fetch.json(f'https://api.github.com/repos/{repo}/git/trees/{sha}')
        if direct.get('truncated'):raise ValueError('Even the direct tree is incomplete')
        for e in direct.get('tree',[]):
            if e['type']=='tree':queue.append((e['sha'],prefix+e['path']+'/'))
            else:result.append({**e,'path':prefix+e['path']})
        if len(result)>350000:raise ValueError('Tree entry budget exceeded')
    return result

def github_assets(c,fetch,source,run):
    repo=source['repo']; sid=source['id']
    meta=fetch.json('https://api.github.com/repos/'+repo)
    branch=meta['default_branch']
    commit=fetch.json('https://api.github.com/repos/'+repo+'/commits/'+quote(branch,safe=''))['sha']
    files=[e for e in complete_tree(fetch,repo,commit) if e['type']=='blob']
    cache=ContentCache(c.path.parent/'content')
    licenses={};license_texts={}
    for e in files:
        if PurePosixPath(e['path']).name.lower() not in {'license','license.txt','license.md','licence.txt','copying','cc0.txt'}: continue
        if not re.search(source.get('license_pattern','.*'),e['path']): continue
        url=f'https://raw.githubusercontent.com/{repo}/{commit}/'+quote(e['path'],safe='/')
        if e['sha'] not in license_texts:
            r=cache.fetch(url,'license.txt',256*1024)
            license_texts[e['sha']]=__import__('pathlib').Path(r['path']).read_text(encoding='utf-8-sig',errors='replace').lower()
        text=license_texts[e['sha']]
        if 'creativecommons.org/publicdomain/zero/1.0' in text or 'cc0 1.0 universal' in text or 'creative commons zero v1.0' in text:
            licenses[str(PurePosixPath(e['path']).parent)]={'spdx':'CC0-1.0','url':f'https://github.com/{repo}/blob/{commit}/'+quote(e['path'],safe='/'),'entry':e}
    if not licenses and repo.startswith('KenneyNL/'):
        readme=next((e for e in files if e['path'].lower()=='readme.md'),None)
        if readme:
            r=cache.fetch(f'https://raw.githubusercontent.com/{repo}/{commit}/README.md','README.md',256*1024)
            text=__import__('pathlib').Path(r['path']).read_text(encoding='utf-8-sig',errors='replace')
            if re.search(r'Assets included in this package[^\n]+CC0 licensed',text,re.I):
                licenses['.']={'spdx':'CC0-1.0','url':f'https://github.com/{repo}/blob/{commit}/README.md','entry':readme}
    if not licenses: raise RuntimeError('No verified scoped CC0 license found; no media promoted from the software license')
    groups=defaultdict(list);by_parent=defaultdict(list);shared_by_root=defaultdict(list)
    def scope(path):
        matches=[root for root in licenses if root=='.' or path.startswith(root+'/')]
        return max(matches,key=len) if matches else None
    for e in files:
        root=scope(e['path'])
        if root is not None:
            by_parent[(root,str(PurePosixPath(e['path']).parent))].append(e)
            if '/textures/' in ('/'+e['path'].lower()) and PurePosixPath(e['path']).suffix.lower() in {'.png','.jpg','.jpeg','.webp'}:shared_by_root[root].append(e)
        path=e['path']; ext=PurePosixPath(path).suffix.lower().lstrip('.')
        if ext not in MEDIA or not re.search(source.get('path_pattern','.*'),path) or not acceptable(path): continue
        root=scope(path)
        if root is None: continue
        kind=MEDIA[ext]
        lower=path.lower()
        if kind=='model-3d' and ('/animations/' in lower or '/animation/' in lower): kind='animation-3d'
        if kind=='texture' and source.get('image_kind') and not re.search(r'(?:^|/)(?:3d|textures?|materials?)(?:/|$)',lower): kind=source['image_kind']
        if kind=='sprite' and re.search(r'(?:^|/)(?:ui|interfaces?)(?:/|$)',lower):kind='ui-asset'
        stem=PurePosixPath(path).stem
        logical='/'.join(p for p in PurePosixPath(path).parent.parts if p.lower() not in FORMAT_DIRS)
        groups[(root,kind,logical,stem)].append(e)
    count=0
    priorities={'glb':0,'gltf':1,'blend':2,'fbx':3,'obj':4}
    for (root,kind,logical,stem),entries in groups.items():
        entries.sort(key=lambda e:priorities.get(PurePosixPath(e['path']).suffix.lstrip('.').lower(),10))
        primary=entries[0]; lp=licenses[root]
        group_key=hashlib.sha256((kind+'|'+logical+'|'+stem).encode()).hexdigest()[:24]
        url=f'https://github.com/{repo}#asset-'+group_key
        tags=source.get('asset_tags',source.get('tags',[]))+[kind]+list(PurePosixPath(logical).parts)+[stem.replace('_',' ')]
        if not c.upsert(sid,primary['path'],stem.replace('_',' ').replace('-',' '),kind,url,license=lp['spdx'],license_url=lp['url'],author=source.get('author',repo.split('/')[0]),tags=tags,platforms=['web','desktop','mobile','game','film'],formats=sorted({PurePosixPath(e['path']).suffix.lstrip('.').lower() for e in entries}),access_url=f'https://raw.githubusercontent.com/{repo}/{commit}/'+quote(primary['path'],safe='/'),revision=hashlib.sha256(''.join(e['sha'] for e in entries).encode()).hexdigest(),run=run): continue
        aid=hashlib.sha256(url.encode()).hexdigest()[:24]
        bundle=[]
        parents={str(PurePosixPath(e['path']).parent) for e in entries}
        dependencies=[e for parent in parents for e in by_parent[(root,parent)] if PurePosixPath(e['path']).suffix.lower() in {'.bin','.mtl','.png','.jpg','.jpeg','.webp'}] if kind in {'model-3d','animation-3d','scene-3d'} else []
        # Shared atlas textures shipped under the same pack license are real dependencies.
        shared=shared_by_root[root]
        if kind in {'model-3d','animation-3d','scene-3d'} and len(shared)<=16: dependencies+=shared
        unique={e['path']:e for e in entries+dependencies+[lp['entry']]}
        for e in by_parent[(root,root)]:
            if PurePosixPath(e['path']).name.lower()=='source.md':unique[e['path']]=e
        for path,e in unique.items():
            role='main' if e==primary else 'variant' if e in entries else 'license' if e==lp['entry'] else 'provenance' if PurePosixPath(path).name.lower()=='source.md' else 'dependency'
            bundle.append({'url':f'https://raw.githubusercontent.com/{repo}/{commit}/'+quote(path,safe='/'),'filename':PurePosixPath(path).name,'relative_path':path,'bytes':e.get('size'),'sha':e['sha'],'role':role})
        previews=[{'url':b['url']} for b in bundle if b['role']=='main' and b['filename'].lower().endswith(('.png','.jpg','.webp'))]
        c.set_details(aid,{'pack_name':repo+' / '+root,'pack_scope':root,'description':source.get('description',meta.get('description') or ''),'files':bundle,'previews':previews[:1],'features':{'pack':repo,'style':source.get('style',''),'license_scope':root,'format_variants':len(entries),'creator_provenance':'Repository maintainer identity is not assumed to be the original artist. Read pack SOURCE.md and original license notices where provided.','animation_inspection':'inspect_3d_asset checks actual glTF skin/clip data'},'commit':commit})
        count+=1
        if count%1000==0:
            c.db.commit();print(__import__('json').dumps({'progress':'github-assets','source':sid,'items':count}),flush=True)
    if not count: raise RuntimeError('No licensed media matched this source; update its scope')
    c.reconcile(sid,run)
    return count

def fuel(c,fetch,run,max_pages=2000):
    count=0; complete=False
    license_map={'Creative Commons Zero v1.0 Universal':'CC0-1.0','Creative Commons Attribution 4.0 International':'CC-BY-4.0','Creative Commons Attribution 3.0 Unported':'CC-BY-3.0'}
    for page in range(1,max_pages+1):
        rows=fetch.json(f'https://fuel.gazebosim.org/1.0/models?per_page=100&page={page}')
        if not isinstance(rows,list): raise ValueError('Unexpected Fuel inventory shape')
        for m in rows:
            if m.get('private') or m.get('permission') not in (0,None): continue
            title=m['name']; owner=m['owner']; sid='fuel:'+owner
            if not acceptable(title+' '+m.get('description','')): continue
            lic=license_map.get(m.get('license_name'),'unknown')
            lu=(m.get('license_url') or '').replace('http://','https://',1)
            base='https://fuel.gazebosim.org/1.0/'+quote(owner,safe='')+'/models/'+quote(title,safe='')
            c.source({'id':sid,'name':owner+' / Open Robotics Fuel','url':'https://fuel.gazebosim.org/1.0/'+quote(owner),'adapter':'fuel','status':'per-model-license-metadata','access':'public','media':['model-3d']})
            tags=['3d','robotics','scene','props']+m.get('categories',[])+[m.get('description','')[:800]]
            if owner=='GoogleResearch': tags+=['photogrammetry','realistic','scanned','photorealistic','household']
            if c.upsert(sid,title,title.replace('_',' '),'model-3d',base,license=lic,license_url=lu,author=owner,tags=tags,platforms=['desktop','game','film'],formats=['zip','obj','sdf','png'] if owner=='GoogleResearch' else ['zip'],access_url=base+'/tip/'+quote(title,safe='')+'.zip',revision=m.get('modify_date',m.get('updatedAt','')),mode='usable' if lic in LICENSES else 'reference',run=run):
                aid=hashlib.sha256(base.encode()).hexdigest()[:24]
                thumb=m.get('thumbnail_url','')
                c.set_details(aid,{'description':m.get('description',''),'files':[{'url':base+'/tip/'+quote(title,safe='')+'.zip','filename':title+'.zip','bytes':m.get('filesize'),'role':'main'}] if lic in LICENSES else [],'previews':[{'url':'https://fuel.gazebosim.org/1.0'+thumb}] if thumb.startswith('/') and lic in LICENSES else [],'features':{'publisher':owner,'categories':m.get('categories',[]),'mesh_formats':'Archive inventory reveals actual meshes and textures; no format is assumed guaranteed.'}})
                count+=1
        c.db.commit()
        print(__import__('json').dumps({'progress':'fuel','page':page,'records':count}),flush=True)
        if len(rows)<100: complete=True; break
    if not complete: raise RuntimeError('Fuel page budget exhausted; valid records retained without source removal')
    for row in c.db.execute("SELECT id FROM sources WHERE id LIKE 'fuel:%'"):
        c.reconcile(row[0],run)
    return count

def khronos(c,fetch,run):
    """Per-model legal metadata, including third-party rights, never the repository license."""
    repo='KhronosGroup/glTF-Sample-Assets'; sid='khronos-assets'
    meta=fetch.json('https://api.github.com/repos/'+repo)
    commit=fetch.json('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])['sha']
    tree=fetch.json(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1')
    if tree.get('truncated'): raise ValueError('Khronos tree incomplete')
    entries=[e for e in tree['tree'] if e['type']=='blob']
    c.source({'id':sid,'name':'Khronos glTF Sample Assets','url':'https://github.com/'+repo,'repo':repo,'adapter':'khronos','status':'per-model-legal-metadata','media':['model-3d']})
    count=0
    for entry in entries:
        if not re.fullmatch(r'Models/[^/]+/metadata.json',entry['path']): continue
        root=str(PurePosixPath(entry['path']).parent)
        raw=f'https://raw.githubusercontent.com/{repo}/{commit}/'
        info=fetch.json(raw+quote(entry['path'],safe='/'))
        legal=info.get('legal',[]); spdxs={x.get('spdx',x.get('license','unknown')) for x in legal}
        allowed=bool(spdxs) and spdxs<=LICENSES
        lic=next((x for x in ('CC-BY-4.0','CC-BY-3.0','MIT','CC0-1.0') if x in spdxs),'unknown')
        files=[e for e in entries if e['path'].startswith(root+'/')]
        models=[e for e in files if PurePosixPath(e['path']).suffix.lower() in {'.glb','.gltf'}]
        if not models: continue
        models.sort(key=lambda e:(not e['path'].endswith('.glb'),'Draco' in e['path'],e['path']))
        canonical=f'https://github.com/{repo}/blob/{meta["default_branch"]}/{quote(root,safe="/")}/README.md'
        title=info.get('name',root.split('/')[-1]); summary=info.get('summary','')
        if not c.upsert(sid,root,title,'model-3d',canonical,license=lic,license_url=raw+quote(entry['path'],safe='/'),author='; '.join(dict.fromkeys(x.get('artist','') for x in legal)),tags=info.get('tags',[])+['gltf','pbr',summary],platforms=['web','desktop','mobile','game','film'],formats=sorted({PurePosixPath(e['path']).suffix.lstrip('.') for e in models}),access_url=raw+quote(models[0]['path'],safe='/'),revision=hashlib.sha256(''.join(e['sha'] for e in files).encode()).hexdigest(),mode='usable' if allowed else 'reference',run=run): continue
        aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
        bundle=[]
        for m in models:
            folder=str(PurePosixPath(m['path']).parent)
            deps=[e for e in files if e['path'].startswith(folder+'/') and e not in models and PurePosixPath(e['path']).suffix.lower() in {'.bin','.png','.jpg','.jpeg','.ktx2','.webp'}]
            for e in [m]+deps:
                bundle.append({'url':raw+quote(e['path'],safe='/'),'filename':PurePosixPath(e['path']).name,'relative_path':e['path'],'sha':e['sha'],'bytes':e.get('size'),'bundle_key':folder,'role':'variant' if e==m else 'dependency'})
        for e in files:
            if PurePosixPath(e['path']).name in {'LICENSE.md','metadata.json'}:
                bundle.append({'url':raw+quote(e['path'],safe='/'),'filename':PurePosixPath(e['path']).name,'relative_path':e['path'],'sha':e['sha'],'bytes':e.get('size'),'role':'license'})
        screenshot=info.get('screenshot',''); preview=raw+quote(root+'/'+screenshot,safe='/') if screenshot and '..' not in PurePosixPath(screenshot).parts else ''
        c.set_details(aid,{'description':summary,'files':bundle if allowed else [],'previews':[{'url':preview}] if preview and allowed else [],'legal':legal,'features':{'publisher':'Khronos','tags':info.get('tags',[]),'rights':'All component notices apply; any unknown, noncommercial or trademark-only legal entry keeps this model reference-only.'}})
        count+=1
    c.reconcile(sid,run); return count
