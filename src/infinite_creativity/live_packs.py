"""Creator packs and original members, queried directly without retained inventories."""
import html,json,re
from pathlib import PurePosixPath
from urllib.parse import quote,urljoin,urlsplit
from .asset_adapters import MEDIA
from .policy import acceptable

def title(body,fallback):
    text=next(iter(re.findall(r'<h1[^>]*>(.*?)</h1>',body,re.S)),fallback)
    return ' '.join(html.unescape(re.sub('<[^>]+>',' ',text)).split())[:250]

def quaternius(http,s,f,after,limit,key=None):
    from .live_providers import item,window,matches
    from .drive import public_entries
    pack=f.get('_pack_key') or (key.split('|',1)[0] if key else '')
    if pack:
        slug,_,folder=pack.partition('@')
        if not re.fullmatch('[A-Za-z0-9_-]+',slug):raise ValueError('Invalid creator pack slug')
        page='https://quaternius.com/packs/'+slug+'.html';body=http.text(page)
        if not re.search(r'CC0|creativecommons.org/publicdomain/zero',body,re.I):raise ValueError('Current creator page does not verify free CC0 pack rights')
        folders=sorted(set(re.findall('https://drive.google.com/drive/folders/([A-Za-z0-9_-]{10,100})',html.unescape(body))))
        if not folders:raise ValueError('This pack requires a different creator distribution flow; no paid/authenticated download is bypassed')
        if key and '|' not in key:
            a=item(s['id'],key,title(body,slug),'asset-pack','CC0-1.0',page,'Quaternius',['cartoon','stylized','3d',slug],pack=key);a['member_kind']='model-3d';return a
        rows=[]
        for fid in ([folder] if folder else folders):
            if not re.fullmatch('[A-Za-z0-9_-]{10,100}',fid):raise ValueError('Invalid public folder identifier')
            for e in public_entries(http.text('https://drive.google.com/drive/folders/'+fid)):
                if not acceptable(e['name']) or re.search(r'\b(?:pro|premium|paid)\b',e['name'],re.I):continue
                if e['mime']=='application/vnd.google-apps.folder':
                    a=item(s['id'],slug+'@'+e['id'],e['name'],'asset-pack','CC0-1.0',page,'Quaternius',[slug,'3d','cartoon'],pack=slug+'@'+e['id']);a['member_kind']='model-3d'
                else:
                    ext=PurePosixPath(e['name']).suffix.lstrip('.').lower()
                    if ext not in MEDIA:continue
                    locator=slug+'@'+fid+'|'+e['id']+'|'+e['name']
                    a=item(s['id'],locator,e['name'],MEDIA[ext],'CC0-1.0',page,'Quaternius',[slug,'3d','cartoon'],[ext],files=[{'url':'https://drive.usercontent.google.com/download?id='+quote(e['id'])+'&export=download','filename':e['name'],'relative_path':e['name'],'role':'main'}],pack=slug+'@'+fid,revision='public-live-file:'+e['id'])
                rows.append(a)
        if key:
            a=next((a for a in rows if a['key']==key),None)
            if not a:raise ValueError('Creator-linked folder member is no longer public')
            return a
        return window(rows,after,limit,f)
    root=http.text('https://quaternius.com/');pages=sorted(set(re.findall(r'''href=["']((?:\./|/)?packs/[A-Za-z0-9_-]+\.html)["']''',root)));rows=[]
    for path in pages:
        slug=PurePosixPath(path).stem
        if slug<=after:continue
        page=urljoin('https://quaternius.com/',path);body=http.text(page)
        if not re.search(r'CC0|creativecommons.org/publicdomain/zero',body,re.I):continue
        a=item(s['id'],slug,title(body,slug),'asset-pack','CC0-1.0',page,'Quaternius',['3d','cartoon','stylized',slug],pack=slug);a['member_kind']='model-3d'
        if matches(a,f):rows.append(a)
        if len(rows)>limit:break
    return window(rows,after,limit,f)

def kenney(http,s,f,after,limit,key=None):
    from .live_providers import item,window,matches
    from .content import ContentCache
    from tempfile import TemporaryDirectory
    pack=f.get('_pack_key') or (key.split('|',1)[0] if key else '')
    if pack:
        if not re.fullmatch('[a-z0-9-]+',pack):raise ValueError('Invalid official pack slug')
        page='https://kenney.nl/assets/'+pack;body=http.text(page)
        if not re.search('CC0|creativecommons.org/publicdomain/zero',body,re.I):raise ValueError('Official pack dedication not verified on current page')
        if key and '|' not in key:
            a=item(s['id'],pack,title(body,pack),'asset-pack','CC0-1.0',page,'Kenney',[pack,'game'],pack=pack);a['member_kind']='model-3d' if '3D' in body else 'sprite';return a
        archives=[urljoin(page,html.unescape(u)) for u in re.findall(r'''href=["']([^"']+\.zip(?:\?[^"']*)?)["']''',body)]
        if not archives:raise ValueError('No direct official free ZIP exposed; paid All-in-1 files are excluded')
        archive=archives[0];rows=[]
        with TemporaryDirectory(prefix='infinite-creativity-zip-request-') as folder:
            cache=ContentCache(folder)
            with cache.remote_zip(archive) as z:
                infos=z.infolist()
                atlases=[v for v in infos if not v.is_dir() and '/textures/' in ('/'+v.filename.lower()) and PurePosixPath(v.filename).suffix.lower() in {'.png','.jpg','.jpeg','.webp','.dds'}]
                for i in infos:
                    path=i.filename;ext=PurePosixPath(path).suffix.lstrip('.').lower();locator=pack+'|'+path
                    if i.is_dir() or ext not in MEDIA or not acceptable(path) or key and locator!=key:continue
                    original={'url':archive,'archive_entry':path,'filename':PurePosixPath(path).name,'relative_path':path,'bytes':i.file_size,'crc32':i.CRC,'role':'main'}
                    dependencies=[v for v in infos if not v.is_dir() and v!=i and ((MEDIA[ext] in {'model-3d','animation-3d','scene-3d'} and PurePosixPath(v.filename).parent==PurePosixPath(path).parent and PurePosixPath(v.filename).suffix.lower() in {'.png','.jpg','.jpeg','.mtl','.bin'}) or PurePosixPath(v.filename).name.lower() in {'license.txt','license.md','cc0.txt'})]
                    if MEDIA[ext] in {'model-3d','animation-3d','scene-3d'} and len(atlases)<=16:
                        dependencies=list({v.filename:v for v in dependencies+atlases}.values())
                    bundle=[original]+[{'url':archive,'archive_entry':v.filename,'filename':PurePosixPath(v.filename).name,'relative_path':v.filename,'bytes':v.file_size,'crc32':v.CRC,'role':'license' if PurePosixPath(v.filename).name.lower() in {'license.txt','license.md','cc0.txt'} else 'dependency'} for v in dependencies]
                    a=item(s['id'],locator,PurePosixPath(path).stem.replace('_',' '),MEDIA[ext],'CC0-1.0',page,'Kenney',[pack,'game',path],[ext],files=bundle,pack=pack,revision=archive+':'+str(i.CRC)+':'+str(i.file_size))
                    a['origin_identity']=page+'|'+re.sub('[^a-z0-9]+','-',PurePosixPath(path).stem.lower()).strip('-');rows.append(a)
        if key:
            if not rows:raise ValueError('Original is no longer in the official free pack')
            return rows[0]
        return window(rows,after,limit,f)
    start='https://kenney.nl/assets'+('?search='+quote(f['query']) if f.get('query') else '')
    cursor=json.loads(after) if after else {'page':start,'after':''};body=http.text(cursor['page']);paths=sorted(set(urlsplit(urljoin(cursor['page'],html.unescape(u))).path for u in re.findall(r'''href=["']([^"']+)''',body) if re.fullmatch('/assets/[a-z0-9-]+',urlsplit(urljoin(cursor['page'],u)).path)));rows=[]
    for path in paths:
        slug=path.rsplit('/',1)[-1]
        if slug<=cursor['after']:continue
        page='https://kenney.nl'+path;p=http.text(page)
        if not re.search('CC0|creativecommons.org/publicdomain/zero',p,re.I):continue
        a=item(s['id'],slug,title(p,slug),'asset-pack','CC0-1.0',page,'Kenney',[slug,'game'],pack=slug);a['member_kind']='model-3d' if '3D' in p else 'sprite'
        if matches(a,f):rows.append(a)
        if len(rows)>limit:break
    result=window(rows,cursor['after'],limit,f)
    if result['next'] is not None:result['next']=json.dumps({'page':cursor['page'],'after':result['next']})
    else:
        n=re.search(r'''href=["']([^"']+)['"][^>]*>\s*(?:Next|›|&gt;|Next page)''',body,re.I)
        result['next']=json.dumps({'page':urljoin(cursor['page'],html.unescape(n[1])),'after':''}) if n else None
    return result
