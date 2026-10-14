"""Fresh audio, model and professional-project provider windows."""
import hashlib,io,json,re,zipfile
from pathlib import PurePosixPath
from urllib.parse import quote,urljoin,urlsplit
from .policy import LICENSES

def fuel(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    offset=int(after or 0);page=offset//100+1;start=offset%100
    if key:
        owner,name=key.split('/',1);base='https://fuel.gazebosim.org/1.0/'+quote(owner,safe='')+'/models/'+quote(name,safe='');data=http.json(base);raw=data if isinstance(data,list) else [data]
    else:raw=http.json(f'https://fuel.gazebosim.org/1.0/models?per_page=100&page={page}')
    rows=[];consumed=start
    for a in raw[start if not key else 0:]:
        consumed+=1
        if a.get('private') or a.get('permission') not in (0,None):continue
        owner=a['owner'];name=a['name'];base='https://fuel.gazebosim.org/1.0/'+quote(owner,safe='')+'/models/'+quote(name,safe='')
        lic={'Creative Commons Zero v1.0 Universal':'CC0-1.0','Creative Commons Attribution 4.0 International':'CC-BY-4.0','Creative Commons Attribution 3.0 Unported':'CC-BY-3.0'}.get(a.get('license_name'),'unknown')
        revision=a.get('modify_date') or a.get('updatedAt') or ''
        original={'url':base+'/tip/'+quote(name,safe='')+'.zip','filename':name+'.zip','role':'main','bytes':a.get('filesize'),'variant':'revision:'+revision}
        thumb=a.get('thumbnail_url','');preview='https://fuel.gazebosim.org/1.0'+thumb if thumb.startswith('/') else thumb
        record=item(s['id'],owner+'/'+name,name.replace('_',' '),'model-3d',lic,(a.get('license_url') or '').replace('http://','https://',1),owner,a.get('categories',[])+[a.get('description','')[:600],'scanned household' if owner=='GoogleResearch' else 'robotics'],['zip'],files=[original] if lic in LICENSES else [],previews=[{'url':preview}] if preview else [],description=a.get('description','')[:600],revision=revision)
        if matches(record,f):rows.append(record)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Fuel model unavailable or rights unverified')
        return rows[0]
    return {'items':rows,'next':str((page-1)*100+consumed) if consumed<len(raw) or len(raw)==100 else None,'total':None,'scope':'Current public Fuel model page, individually declared rights'}

def fsd50k(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    record=http.json('https://zenodo.org/api/records/4060432');files={v['key']:v for v in record['files']};meta=files['FSD50K.metadata.zip']
    body=http.read(meta['links']['self'],16*1024*1024)
    if 'md5:'+hashlib.md5(body).hexdigest()!=meta['checksum']:raise ValueError('Official audio metadata checksum mismatch')
    rows=[]
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for split in ('dev','eval'):
            if f.get('_pack_key') and split!=f['_pack_key']:continue
            if key and not key.startswith(split+':'):continue
            filename=next(n for n in z.namelist() if n.endswith(split+'_clips_info_FSD50K.json'))
            clips=json.loads(z.read(filename))
            names=[f'FSD50K.{split}_audio.z{i:02}' for i in range(1,6 if split=='dev' else 2)]+[f'FSD50K.{split}_audio.zip']
            parts=[{'url':files[n]['links']['self'],'bytes':files[n]['size'],'checksum':files[n]['checksum']} for n in names]
            cid=hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()[:24]
            for n in sorted(clips):
                locator=split+':'+n
                if key is not None and locator!=key:continue
                if key is None and locator<=after:continue
                a=clips[n];evidence=a.get('license','').replace('http://','https://',1)
                lic=next((lic for pattern,lic in [('publicdomain/zero','CC0-1.0'),('/licenses/by/4.0','CC-BY-4.0'),('/licenses/by/3.0','CC-BY-3.0')] if pattern in evidence),'unknown')
                member=f'FSD50K.{split}_audio/{n}.wav'
                original={'url':parts[-1]['url'],'container_id':cid,'archive_entry':member,'filename':n+'.wav','relative_path':member,'role':'main'}
                a=item(s['id'],locator,a.get('title',n),'audio',lic,evidence,str(a.get('uploader',a.get('username',''))),list(a.get('tags',[]))+['sound-effects','FSD50K'],['wav'],files=[original] if lic in LICENSES else [],pack=split,revision=cid)
                a['containers']={cid:{'type':'split-zip','parts':parts,'license_scope':'This recording only; other archive members have independent rights.'}}
                if matches(a,f):rows.append(a)
                if key is None and len(rows)>limit:return {'items':rows[:limit],'next':rows[limit-1]['key'],'total':None,'scope':'Fresh individually licensed audio metadata; no downloaded audio inventory'}
    if key:
        if not rows:raise ValueError('Audio clip no longer appears in the official metadata')
        return rows[0]
    return {'items':rows,'next':None,'total':None,'scope':'Fresh per-clip metadata only'}

def blender_demos(http,s,f,after,limit,key=None):
    from .live_providers import item,window
    from .blender_demos import Cards
    page='https://www.blender.org/download/demo-files/';p=Cards();p.feed(http.text(page));rows=[]
    for card in p.cards:
        text=' '.join(' '.join(card['text']).split())
        links=list(dict.fromkeys(urljoin(page,u) for u in card['links'] if urlsplit(urljoin(page,u)).hostname in {'download.blender.org','www.blender.org'} and urlsplit(u).path.lower().endswith(('.blend','.zip','.mp4','.7z'))))
        if not links or re.search('human base mesh',text,re.I):continue
        locator=links[0]
        if (key or f.get('_pack_key')) and (key or f['_pack_key'])!=locator:continue
        evidence=next((u.replace('http://','https://',1) for u in card['links'] if 'creativecommons.org/licenses/' in u or 'creativecommons.org/publicdomain/' in u),'')
        lic='CC0-1.0' if re.search(r'\bCC-?0\b',text) else 'CC-BY-4.0' if '/by/4.0' in evidence else 'CC-BY-3.0' if '/by/3.0' in evidence else 'unknown'
        if lic=='CC0-1.0':evidence=page
        kind='animation-2d' if re.search('grease|pencil|2d',text,re.I) else 'animation-3d' if re.search('animation|rig|pose',text,re.I) else 'editing-template' if re.search('sequencer|editing',text,re.I) else 'scene-3d'
        rows.append(item(s['id'],locator,text.split('Requires Blender')[0][:180],kind,lic,evidence,'Blender demo authors; read original notices',[text,'Blender'],sorted({PurePosixPath(urlsplit(u).path).suffix.lstrip('.') for u in links}),files=[{'url':u,'filename':PurePosixPath(urlsplit(u).path).name,'role':'main' if i==0 else 'variant'} for i,u in enumerate(links)] if lic!='unknown' else [],previews=[{'url':urljoin(page,u)} for u in card['images'][:1]],description=text,pack=locator,revision=hashlib.sha256(text.encode()).hexdigest()))
    if key:
        if not rows:raise ValueError('Demo no longer public or withheld pending content review')
        return rows[0]
    return window(rows,after,limit,f)

def khronos(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    from .asset_adapters import complete_tree
    repo='KhronosGroup/glTF-Sample-Assets';meta=http.json('https://api.github.com/repos/'+repo);commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])['sha'];entries=complete_tree(http,repo,commit,max_requests=12);raw=f'https://raw.githubusercontent.com/{repo}/{commit}/';rows=[]
    for e in sorted(entries,key=lambda e:e['path']):
        path=e['path']
        if not re.fullmatch('Models/[^/]+/metadata.json',path):continue
        root=str(PurePosixPath(path).parent)
        if key and root!=key or not key and root<=after:continue
        d=http.json(raw+quote(path,safe='/'));legal=d.get('legal',[]);rights={v.get('spdx',v.get('license','unknown')) for v in legal};allowed=bool(rights) and rights<=LICENSES
        lic=next((x for x in ['CC-BY-4.0','CC-BY-3.0','MIT','CC0-1.0'] if x in rights),'unknown') if allowed else 'unknown';scope=[v for v in entries if v['path'].startswith(root+'/') and v['type']=='blob'];models=[v for v in scope if v['path'].endswith(('.glb','.gltf'))]
        if not models:continue
        selected=[v for v in scope if PurePosixPath(v['path']).suffix.lower() in {'.glb','.gltf','.bin','.png','.jpg','.jpeg','.ktx2','.webp'} or PurePosixPath(v['path']).name in {'metadata.json','LICENSE.md'}]
        originals=[{'url':raw+quote(v['path'],safe='/'),'filename':PurePosixPath(v['path']).name,'relative_path':v['path'],'sha':v['sha'],'bytes':v.get('size'),'bundle_key':str(PurePosixPath(v['path']).parent),'role':'variant' if v in models else 'license' if PurePosixPath(v['path']).name in {'metadata.json','LICENSE.md'} else 'dependency'} for v in selected] if allowed else []
        a=item(s['id'],root,d.get('name',root.rsplit('/',1)[-1]),'model-3d',lic,raw+quote(path,safe='/'),'; '.join(dict.fromkeys(v.get('artist','') for v in legal)),d.get('tags',[])+['gltf','pbr'],sorted({PurePosixPath(v['path']).suffix.lstrip('.') for v in models}),files=originals,previews=[{'url':raw+quote(root+'/'+d['screenshot'],safe='/')}] if d.get('screenshot') and allowed else [],description=d.get('summary',''),revision=commit)
        if matches(a,f):rows.append(a)
        if not key and len(rows)>limit:break
    if key:
        if not rows:raise ValueError('Sample asset no longer public or eligible')
        return rows[0]
    return {'items':rows[:limit],'next':rows[limit-1]['key'] if len(rows)>limit else None,'total':None,'scope':'Current sample models with all component legal entries checked'}
