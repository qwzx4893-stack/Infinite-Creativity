"""Official free Kenney packs: enumerate licensed originals through ranged ZIP reads."""
import hashlib
import html
import json
import re
import time
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import urljoin,urlsplit,unquote
from urllib.request import Request
from .content import ContentCache,validate_url
from .asset_adapters import MEDIA,FORMAT_DIRS
from .policy import acceptable

def page(cache,url):
    validate_url(url)
    time.sleep(.2)
    with cache.opener.open(Request(url,headers={'User-Agent':'InfiniteCreativity/0.2 (+https://github.com/qwzx4893-stack/Infinite-Creativity)'}),timeout=45) as response:
        body=response.read(2*1024*1024+1)
    if len(body)>2*1024*1024: raise ValueError('Provider page exceeded metadata budget')
    return body.decode('utf-8')

def pack_urls(cache):
    urls=set(); pending=['https://kenney.nl/assets']; visited=set()
    while pending:
        url=pending.pop(0)
        if url in visited: continue
        visited.add(url)
        if len(visited)>100: raise ValueError('Provider pagination exceeded inventory budget')
        text=page(cache,url)
        for href in re.findall(r'href=[\"\']([^\"\']+)',text):
            link=urljoin(url,html.unescape(href)); p=urlsplit(link)
            if p.hostname!='kenney.nl': continue
            if re.fullmatch('/assets/[a-z0-9-]+',p.path): urls.add('https://kenney.nl'+p.path)
            elif (re.fullmatch(r'/assets/page:\d+',p.path) or (p.path=='/assets' and re.fullmatch(r'page=\d+',p.query))) and link not in visited: pending.append(link)
    if not urls: raise ValueError('No official free asset packs found')
    return sorted(urls)

def inventory(cache,url,metadata,license_page_cc0=False):
    key=hashlib.sha256(url.encode()).hexdigest()
    path=metadata/('zip-'+key+'.inventory.json')
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    with cache.remote_zip(url) as z:
        members=z.infolist()
        if len(members)>100000: raise ValueError('Pack has too many archive entries')
        licenses=[i for i in members if PurePosixPath(i.filename).name.lower() in {'license.txt','license','license.md','cc0.txt'}]
        verified=[]
        for info in licenses:
            if info.file_size>256*1024: continue
            text=z.read(info).decode('utf-8-sig',errors='replace').lower()
            if 'creativecommons.org/publicdomain/zero/1.0' in text or 'cc0 1.0 universal' in text or 'creative commons zero' in text:
                verified.append(info.filename)
        if not verified and not license_page_cc0: raise ValueError('Archive has no explicit CC0 dedication; refusing media promotion')
        entries=[{'path':i.filename,'bytes':i.file_size,'compressed_bytes':i.compress_size,'crc32':i.CRC} for i in members if not i.is_dir()]
    result={'license_files':verified,'entries':entries,'license_evidence':'archive-cc0' if verified else 'official-pack-page-cc0'}
    path.write_text(json.dumps(result),encoding='utf-8')
    return result

def index_pack(c,cache,pack_url,metadata,run):
    text=page(cache,pack_url)
    links=[html.unescape(u) for u in re.findall(r'href=[\"\']([^\"\']+)',text)]
    archives=[urljoin(pack_url,u) for u in links if re.search(r'/media/pages/assets/[^\"\']+\.zip$',u)]
    if not archives: raise ValueError('No official free distribution archive found')
    # The free individual download is explicit. Never follow paid All-in-1 links.
    archive=archives[0]; validate_url(archive)
    explicit_cc0=bool(re.search(r'href=[\"\']https?://creativecommons\.org/publicdomain/zero/1\.0/?[\"\']',text))
    data=inventory(cache,archive,metadata,license_page_cc0=explicit_cc0)
    slug=pack_url.rsplit('/',1)[-1]; sid='kenney-pack:'+slug
    title=slug.replace('-',' ')
    match=re.search(r'/assets/category:([^\"\'<>]+)',text)
    category=unquote(match[1]).lower() if match else '2d'
    category={'user interface':'ui','textures':'texture'}.get(category,category)
    if slug.startswith('ui-') or slug in {'input-prompts','input-prompts-pixel','mobile-controls','cursor-pack','cursor-pixel-pack','crosshair-pack'}: category='ui'
    c.source({'id':sid,'name':'Kenney / '+title,'url':pack_url,'adapter':'kenney-packs','status':data.get('license_evidence','archive-cc0'),'license':'CC0-1.0','media':[category],'distribution':archive})
    groups=defaultdict(list)
    entries=data['entries']
    by_parent=defaultdict(list); atlases=[]
    license_entries=[e for e in entries if e['path'] in data['license_files']]
    for e in entries:
        p=PurePosixPath(e['path']); ext=p.suffix.lower()
        if ext in {'.bin','.mtl'}: by_parent[str(p.parent)].append(e)
        if '/textures/' in ('/'+e['path'].lower()) and ext in {'.png','.jpg','.jpeg'}: atlases.append(e)
    for e in entries:
        path=e['path']; p=PurePosixPath(path); ext=p.suffix.lower().lstrip('.')
        if ext not in MEDIA or not acceptable(path) or '..' in p.parts or p.is_absolute(): continue
        if p.name.lower().startswith(('preview','sample','license')) or '/previews/' in ('/'+path.lower()): continue
        kind=MEDIA[ext]
        if kind=='illustration' and category=='ui': kind='ui-asset'
        if kind=='texture': kind='ui-asset' if category=='ui' else 'texture' if category=='texture' or 'texture' in slug or '/textures/' in ('/'+path.lower()) else 'sprite'
        if kind=='model-3d' and '/animations/' in ('/'+path.lower()): kind='animation-3d'
        logical='/'.join(v for v in p.parent.parts if v.lower() not in FORMAT_DIRS|{'png','svg','vector','vectors','3d assets','2d assets','audio','sprites'})
        groups[(kind,logical,p.stem)].append(e)
    count=0
    for (kind,logical,stem),files in groups.items():
        files.sort(key=lambda e:{'glb':0,'gltf':1,'blend':2,'fbx':3,'obj':4}.get(PurePosixPath(e['path']).suffix.lstrip('.').lower(),10))
        key=hashlib.sha256((kind+'|'+logical+'|'+stem).encode()).hexdigest()[:24]
        canonical=pack_url+'#asset-'+key; aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
        lp=data['license_files'][0] if data['license_files'] else ''
        if not c.upsert(sid,files[0]['path'],stem.replace('_',' ').replace('-',' '),kind,canonical,license='CC0-1.0',license_url=pack_url,author='Kenney',tags=['kenney','game',title,kind,logical,'low-poly' if category=='3d' else category],platforms=['web','desktop','mobile','game','film'],formats=sorted({PurePosixPath(e['path']).suffix.lstrip('.').lower() for e in files}),access_url=archive,revision=hashlib.sha256((archive+json.dumps(files,sort_keys=True)).encode()).hexdigest(),run=run): continue
        parents={str(PurePosixPath(e['path']).parent) for e in files}
        dependencies=[e for parent in parents for e in by_parent[parent]]
        if kind in {'model-3d','animation-3d','scene-3d'}:
            if len(atlases)<=32: dependencies+=atlases
        selected={e['path']:e for e in files+dependencies+license_entries}
        bundle=[{'url':archive,'archive_entry':path,'filename':PurePosixPath(path).name,'relative_path':path,'bytes':e['bytes'],'crc32':e['crc32'],'role':'main' if e==files[0] else 'variant' if e in files else 'license' if path==lp else 'dependency'} for path,e in selected.items()]
        c.set_details(aid,{'files':bundle,'features':{'pack':title,'archive_license_entry':lp,'distribution':'official free individual pack','access':'selected ZIP members via HTTPS ranges; CRC32 verified; local SHA256 after retrieval','format_variants':len(files)}})
        count+=1
    if not count: raise ValueError('Official pack contained no eligible media')
    c.reconcile(sid,run); c.db.commit()
    return count

def kenney(c,fetch,run):
    cache=ContentCache(c.path.parent/'content'); metadata=fetch.cache
    count=0; failures=[]
    urls=pack_urls(cache)
    for pack_url in urls:
        try:
            n=index_pack(c,cache,pack_url,metadata,run); count+=n
            print(json.dumps({'progress':'kenney-packs','pack':pack_url.rsplit('/',1)[-1],'records':n,'total':count}),flush=True)
        except Exception as e:
            failures.append({'pack':pack_url,'error':str(e)[:300]})
            print(json.dumps({'progress':'kenney-packs','failed':failures[-1]}),flush=True)
    if failures: raise RuntimeError(f'{len(failures)} free pack failures; valid items retained. '+json.dumps(failures[:5]))
    return count
