"""Only public, creator-linked Google Drive distributions with explicit pack rights."""
import hashlib
import html
import json
import re
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin,quote
from .content import ContentCache
from .policy import acceptable
from .asset_adapters import MEDIA,FORMAT_DIRS

def public_entries(document):
    match=re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'((?:\\.|[^'\\])*)'",document)
    if not match:raise ValueError('No public folder inventory; authentication, provider changes or unavailable sharing')
    encoded=re.sub(r'\\x([0-9a-fA-F]{2})',lambda m:'\\u00'+m[1],match[1]).replace("\\'","'")
    decoded=json.loads('"'+encoded.replace('"','\\"')+'"')
    payload=json.loads(decoded)
    if not isinstance(payload,list) or not payload or not isinstance(payload[0],list):raise ValueError('Unknown public folder inventory shape')
    rows=payload[0]
    # This bounded HTML connector accepts only short lists: large lists do not
    # expose a trustworthy completion marker here. An API connector can expand them.
    if len(rows)>=50:raise ValueError('Public folder listing may be paginated; refusing to mark it complete')
    result=[]
    for row in rows:
        if not isinstance(row,list) or len(row)<4 or not re.fullmatch('[A-Za-z0-9_-]{10,100}',str(row[0])):raise ValueError('Invalid public Drive entry')
        name=row[2]
        if not isinstance(name,str) or '/' in name or '\\' in name or name in {'.','..'}:raise ValueError('Unsafe Drive entry name')
        result.append({'id':row[0],'name':name,'mime':row[3]})
    return result

def crawl(cache,folder,max_folders=300):
    queue=[(folder,'')];seen=set();files=[]
    while queue:
        fid,parent=queue.pop(0)
        if fid in seen:continue
        if len(seen)>=max_folders:raise ValueError('Public folder budget exceeded; no partial reconciliation')
        seen.add(fid)
        # Cache HTML for a day, then refresh: content hashes do not attest to a live folder listing.
        receipt=cache.fetch('https://drive.google.com/drive/folders/'+fid,'folder.html',8*1024*1024,cache_revision=str(int(time.time()//86400)))
        for entry in public_entries(Path(receipt['path']).read_text(encoding='utf-8')):
            if re.search(r'\b(?:pro|premium|paid)\b',entry['name'],re.I):continue
            path=str(PurePosixPath(parent)/entry['name'])
            if entry['mime']=='application/vnd.google-apps.folder':queue.append((entry['id'],path))
            elif not entry['mime'].startswith('application/vnd.google-apps.'):files.append({**entry,'path':path})
    return files

def quaternius(c,fetch,run):
    cache=ContentCache(c.path.parent/'content');day=str(int(time.time()//86400))
    root=cache.fetch('https://quaternius.com/','index.html',4*1024*1024,cache_revision=day)
    document=Path(root['path']).read_text(encoding='utf-8')
    pages=sorted(set(urljoin('https://quaternius.com/',p) for p in re.findall(r'''href=["']((?:\./|/)?packs/[A-Za-z0-9_-]+\.html)["']''',document)))
    if not pages:raise ValueError('Official pack index unavailable')
    count=0;complete=0;unsupported=[];failed=[]
    for page in pages:
        try:
            receipt=cache.fetch(page,'pack.html',4*1024*1024,cache_revision=day);body=Path(receipt['path']).read_text(encoding='utf-8')
            if not re.search(r'(?:CC0|creativecommons.org/publicdomain/zero)',body,re.I):unsupported.append(page);continue
            folders=sorted(set(re.findall(r'https://drive.google.com/drive/folders/([A-Za-z0-9_-]{10,100})',html.unescape(body))))
            if not folders:unsupported.append(page);continue
            slug=PurePosixPath(page).stem;sid='quaternius:'+slug
            title=html.unescape(re.sub('<[^>]+>',' ',next(iter(re.findall(r'<h1[^>]*>(.*?)</h1>',body,re.S)),slug)))
            title=' '.join(title.split())[:200] or slug
            c.source({'id':sid,'name':title,'url':page,'adapter':'public-drive','status':'official-creator-linked-CC0','media':['model-3d','animation-3d','texture'],'author':'Quaternius'})
            inventory=[]
            for folder in folders:inventory+=crawl(cache,folder)
            groups={}
            for entry in inventory:
                path=PurePosixPath(entry['path']);ext=path.suffix.lower().lstrip('.')
                if ext not in MEDIA or not acceptable(entry['path']):continue
                logical='/'.join(p for p in path.parent.parts if p.lower() not in FORMAT_DIRS|{'blends','fbxs','objs','fbx files','obj files','blend files','gltf files'})
                kind=MEDIA[ext];key=(kind,logical,path.stem.lower())
                groups.setdefault(key,[]).append(entry)
            n=0
            for (kind,logical,stem),entries in groups.items():
                entries.sort(key=lambda e:({'glb':0,'gltf':1,'blend':2,'fbx':3,'obj':4}.get(PurePosixPath(e['path']).suffix.lstrip('.'),10),e['path']))
                canonical=page+'#asset-'+hashlib.sha256((kind+'|'+logical+'|'+stem).encode()).hexdigest()[:24]
                tags=['cartoon','stylized','low-poly',title,logical,stem]
                original=[{'url':'https://drive.usercontent.google.com/download?id='+e['id']+'&export=download','filename':e['name'],'relative_path':e['path'],'role':'main' if i==0 else 'variant','drive_id':e['id']} for i,e in enumerate(entries)]
                # Public HTML does not attest to file-revision metadata. Refresh originals daily.
                revision=hashlib.sha256((day+'|'+json.dumps(entries,sort_keys=True)).encode()).hexdigest()
                if not c.upsert(sid,entries[0]['id'],entries[0]['name'].rsplit('.',1)[0],kind,canonical,license='CC0-1.0',license_url=page,author='Quaternius',tags=tags,platforms=['game','film','desktop','web','mobile'],formats=sorted({PurePosixPath(e['path']).suffix.lstrip('.') for e in entries}),access_url=original[0]['url'],revision=revision,run=run):continue
                aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
                c.set_details(aid,{'pack_name':title,'pack_scope':slug,'description':'Original creator-linked public Drive files in a themed CC0 pack. Individual format variants are grouped.','files':original,'features':{'public_drive':True,'theme':title,'license_scope':page,'dependency_limit':'Inspect original blend/FBX/OBJ content; any separately referenced textures must be selected from the same licensed pack.'}});n+=1
            if not n:raise ValueError('Creator folder exposes no supported original media')
            c.reconcile(sid,run);c.db.commit();count+=n;complete+=1
            print(json.dumps({'progress':'quaternius','pack':slug,'items':n}),flush=True)
        except Exception as e:
            if 'may be paginated' in str(e):unsupported.append(page+' (public listing completeness unavailable)')
            else:failed.append({'page':page,'error':str(e)[:300]})
            c.db.commit()
    path=fetch.cache/'quaternius-coverage.json';path.write_text(json.dumps({'official_pages':len(pages),'complete_drive_packs':complete,'items':count,'unsupported_distribution_pages':unsupported,'failed':failed},indent=2),encoding='utf-8')
    c.source({'id':'quaternius','name':'Quaternius public Drive distributions','url':'https://quaternius.com/','adapter':'public-drive','status':'complete-supported-pack-listings','coverage':{'official_pages':len(pages),'complete_drive_packs':complete,'indexed_items':count,'unsupported_distribution_pages':unsupported,'failed':failed,'whole_provider_indexed':False}})
    if failed:raise ValueError(f'{len(failed)} public pack listings incomplete; completed packs preserved. See state/http/quaternius-coverage.json')
    return count
