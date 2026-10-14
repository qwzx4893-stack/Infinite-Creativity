"""Official authenticated APIs and versioned public creative software packages."""
import io,json,os,re,tarfile
from pathlib import PurePosixPath
from urllib.parse import urlencode,quote,urlsplit
from .policy import LICENSES
from .live_catalogs import cc_license,original,plain


def freesound(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    if not os.environ.get('FREESOUND_TOKEN') and not os.environ.get('FREESOUND_OAUTH_TOKEN'):
        raise ValueError('Official FREESOUND_TOKEN required; original downloads require FREESOUND_OAUTH_TOKEN')
    position=int(after or 0)
    if key:
        if not key.isdigit():raise ValueError('Invalid sound ID')
        data={'results':[http.json('https://freesound.org/apiv2/sounds/'+key+'/')]}
    else:
        params={'query':f.get('query') or f.get('style') or 'ambience','page':position//20+1,'page_size':20,
                'filter':'license:("Creative Commons 0" OR "Attribution" OR "Attribution 3.0")',
                'fields':'id,name,username,license,description,tags,type,filesize,previews,download,url,duration,samplerate,bitrate,channels'}
        data=http.json('https://freesound.org/apiv2/search/text/?'+urlencode(params))
    rows=[];consumed=position%20
    for x in data.get('results',[])[consumed if not key else 0:]:
        consumed+=1;lic,evidence=cc_license(x.get('license'));files=[]
        if key and os.environ.get('FREESOUND_OAUTH_TOKEN') and lic in LICENSES and x.get('download'):
            files=[original(http,x['download'],x['name'],bytes=x.get('filesize'))]
        a=item(s['id'],str(x['id']),x['name'],'audio',lic,evidence,x.get('username',''),x.get('tags',[]),[x.get('type','wav')],files=files,description=plain(x.get('description')),revision=str(x.get('filesize',''))+str(x.get('duration','')))
        a['origin_url']=x.get('url','');a['original_access']='official-oauth-download' if files else 'FREESOUND_OAUTH_TOKEN-required-for-originals'
        a['features']={k:x.get(k) for k in ['duration','samplerate','bitrate','channels']}
        if key or matches(a,{**f,'query':''}):rows.append(a)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Current sound unavailable')
        return rows[0]
    n=position//20*20+consumed
    return {'items':rows,'next':str(n) if n<data.get('count',0) else None,'total':None,'scope':'Current official Freesound account API; per-recording licence, no preview-as-original substitution'}


def cgtrader(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    if not os.environ.get('CGTRADER_TOKEN'):raise ValueError('Official CGTRADER_TOKEN / developer API access required')
    position=int(after or 0)
    if key:
        if not key.isdigit():raise ValueError('Invalid CGTrader ID')
        current=http.json('https://api.cgtrader.com/v1/models/'+key);data={'models':[current.get('model',current)]}
    else:
        params={'keywords':f.get('query') or f.get('style') or 'stylized','page':position//20+1,'per_page':20,
                'adult_content':'false','license':'exclude_editorial','max_price':0,'min_admin_rating':5,'sort':'best_match'}
        data=http.json('https://api.cgtrader.com/v1/models?'+urlencode(params))
    rows=[];consumed=position%20
    for x in data.get('models',[])[consumed if not key else 0:]:
        consumed+=1
        if x.get('adult_content') or x.get('only_for_adults'):continue
        previews=[{'url':u} for u in x.get('thumbnails',[]) if isinstance(u,str) and u.startswith('https://')]
        for p in previews:http.approve_content(p['url'])
        a=item(s['id'],str(x['id']),x['title'],'visual-reference','unknown','https://www.cgtrader.com/pages/terms-and-conditions',x.get('author_name',''),x.get('tags',[]),x.get('availableFileExtensions',[]),previews=previews,description=plain(x.get('raw_description') or x.get('description')),reference_preview=bool(previews))
        a['reference_category']='three-d';a['origin_url']=x.get('url','');a['features']={k:x.get(k) for k in ['animated','rigged','game_ready','info','prices','license']}
        a['original_access']='Current royalty-free/custom licence scope unresolved; originals withheld even when price is zero'
        if key or matches(a,{**f,'query':''}):rows.append(a)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Model unavailable or provider flagged adult content')
        return rows[0]
    n=position//20*20+consumed
    return {'items':rows,'next':str(n) if n<data.get('total',0) else None,'total':None,'scope':'Official developer API, free-price public presentations; rights are not inferred from price'}


def dribbble(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    if not os.environ.get('DRIBBBLE_TOKEN'):raise ValueError('Official DRIBBBLE_TOKEN required; API v2 is account-scoped, not an aggregated gallery API')
    position=int(after or 0)
    if key:
        if not key.isdigit():raise ValueError('Invalid shot ID')
        raw=[http.json('https://api.dribbble.com/v2/shots/'+key)]
    else:raw=http.json(f'https://api.dribbble.com/v2/user/shots?page={position//20+1}&per_page=20')
    rows=[];consumed=position%20
    for x in raw[consumed if not key else 0:]:
        consumed+=1;images=x.get('images',{});url=images.get('normal') or images.get('hidpi') or images.get('teaser');previews=[]
        if url:http.approve_content(url);previews=[{'url':url}]
        a=item(s['id'],str(x['id']),x['title'],'visual-reference',author=(x.get('user') or {}).get('name',''),tags=x.get('tags',[]),previews=previews,description=plain(x.get('description')),revision=x.get('updated_at',''),reference_preview=bool(previews));a['reference_category']='interface';a['origin_url']=x.get('html_url','')
        if key or matches(a,f):rows.append(a)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Shot no longer accessible')
        return rows[0]
    n=position//20*20+consumed
    return {'items':rows,'next':str(n) if consumed<len(raw) or len(raw)==20 else None,'total':None,'scope':'Official account-scoped Dribbble presentations only'}


def npm_package(http,s,f,after,limit,key=None):
    from .live_providers import item,window
    package=s['npm'];metadata=http.json('https://registry.npmjs.org/'+quote(package,safe=''));version=metadata['dist-tags']['latest'];v=metadata['versions'][version]
    licence=v.get('license','unknown');licence=licence.get('type','unknown') if isinstance(licence,dict) else licence
    if licence not in LICENSES:raise ValueError('Current package does not declare a supported licence')
    url=v['dist']['tarball'];http.approve_content(url)
    # Selected package only, streamed into this request's memory. Source members
    # are not imported, installed, evaluated or saved in the repository.
    body=http.read(url,8*1024*1024);rows=[]
    import hashlib
    expected=v['dist'].get('shasum')
    if expected and hashlib.sha1(body).hexdigest()!=expected:raise ValueError('Current npm package integrity mismatch')
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as archive:
        members=[x for x in archive.getmembers() if x.isfile() and x.size<=2*1024*1024 and not x.name.startswith('/') and '..' not in PurePosixPath(x.name).parts]
        legal=next((x for x in members if PurePosixPath(x.name).name.lower() in {'license','license.md','license.txt'}),None)
        if not legal:raise ValueError('Package notice missing; no original members exposed')
        notice=archive.extractfile(legal).read().decode(errors='replace')
        if licence=='MIT' and 'permission is hereby granted, free of charge' not in notice.lower():raise ValueError('MIT notice does not match package licence')
        if key=='@package':
            a=item(s['id'],key,package+' '+version,'asset-pack',licence,'https://www.npmjs.com/package/'+package,str(v.get('author','')),['javascript','motion'],['js'],pack='@package',revision=version);a['software_only']=True;a['member_kind']='motion';return a
        for member in members:
            if not member.name.endswith(('.js','.mjs','.cjs','.ts','.css')) or member.name.endswith('.d.ts'):continue
            if key and key!=member.name:continue
            content=archive.extractfile(member).read()
            # Library's inline-original support stores bytes only in RAM until
            # an explicitly selected read creates its short-lived parser file.
            files=[{'url':url,'filename':PurePosixPath(member.name).name,'relative_path':member.name,'tar_entry':member.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'role':'main'},
                   {'url':url,'filename':PurePosixPath(legal.name).name,'relative_path':legal.name,'tar_entry':legal.name,'sha256':hashlib.sha256(notice.encode()).hexdigest(),'bytes':len(notice.encode()),'role':'license'}]
            a=item(s['id'],member.name,package+' / '+PurePosixPath(member.name).name,'motion',licence,'https://www.npmjs.com/package/'+package,str(v.get('author','')),['javascript','motion','web',package],[PurePosixPath(member.name).suffix.lstrip('.')],files=files,pack='@package',revision=version)
            a['software_only']=True;rows.append(a)
    if key:
        if not rows:raise ValueError('Current package member unavailable')
        return rows[0]
    return window(rows,after,limit,f)
