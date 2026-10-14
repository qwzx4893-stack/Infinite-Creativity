"""Official authenticated APIs and versioned public creative software packages."""
import io,json,os,re,tarfile
from pathlib import PurePosixPath
from urllib.parse import urlencode,quote,urlsplit
from .policy import LICENSES
from .live_catalogs import cc_license,original,plain


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
