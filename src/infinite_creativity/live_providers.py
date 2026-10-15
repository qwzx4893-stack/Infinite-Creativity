"""Provider inventories materialized only for the current live MCP request."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote,urljoin,urlsplit
from .asset_adapters import MEDIA,FORMAT_DIRS,complete_tree
from .codrops import code_entries
from .policy import LICENSES,LICENSE_NAMES,acceptable,review_terms,styles_for,normalize_query
from .organization import classify

def item(source,key,title,kind,license='unknown',license_url='',author='',tags=(),formats=(),files=(),previews=(),description='',pack='',revision='',reference_preview=False):
    tags=list(tags)
    text=(title+' '+' '.join(tags)+' '+description).lower()
    platforms=[]
    if re.search(r'\b(react|vue|svelte|html|css|web|nextjs|tailwind)\b',text) or set(formats)&{'html','css','tsx','jsx','vue','svelte'}:platforms.append('web')
    if re.search(r'\b(flutter|react.native|android|ios|swiftui|mobile)\b',text) or set(formats)&{'swift','dart'}:platforms.append('mobile')
    if re.search(r'\b(avalonia|winui|wpf|desktop|qt|gtk)\b',text) or set(formats)&{'xaml'}:platforms.append('desktop')
    if re.search(r'\b(godot|unity|unreal|game|tileset|sprite)\b',text):platforms.append('game')
    if re.search(r'\b(blender|cinematic|film|movie|animation)\b',text):platforms.append('film')
    return {'source':source,'key':key,'title':title,'kind':kind,'license':license,'license_url':license_url,'author':author,'tags':tags,'styles':styles_for(text),'formats':list(formats),'platforms':platforms,'files':list(files),'previews':list(previews),'description':description,'pack':pack,'revision':revision,'reference_preview':reference_preview}

def matches(a,f):
    text=a['title']+' '+' '.join(a['tags'])+' '+a.get('description','')+' '+a['key']
    if not acceptable(text) or review_terms(text):return False
    usable=(a['license'] in LICENSES or a.get('end_product_only_verified')) and bool(a['license_url'])
    if f.get('mode','usable')=='usable' and not usable:return False
    if f.get('mode')=='reference' and usable:return False
    for name in ('kind','license'):
        if f.get(name) and a[name]!=f[name]:return False
    for singular,plural in [('style','styles'),('format','formats'),('platform','platforms')]:
        if f.get(singular) and normalize_query(f[singular]) not in a[plural]:return False
    section=classify({'kind':a.get('member_kind',a['kind']),'title':a['title'],'tags':a['tags'],'upstream_id':a['key'],'reference_category':a.get('reference_category','')})[0]
    if f.get('section') and section!=f['section'] and not section.startswith(f['section']+'/'):return False
    words=normalize_query(f.get('query','')).split()
    text=(a['title']+' '+' '.join(a['tags'])+' '+' '.join(a['styles'])+' '+a['description']).lower()
    return all(word in text for word in words)

def window(rows,after,limit,filters):
    selected=[];last=after;more=False
    for a in sorted(rows,key=lambda x:str(x['key'])):
        if str(a['key'])<=after:continue
        if not matches(a,filters):continue
        if len(selected)==limit:more=True;break
        selected.append(a);last=str(a['key'])
    return {'items':selected,'next':last if more else None,'scope':'Current provider response; no retained asset index','total':None}

def polyhaven(http,s,f,after,limit,key=None):
    data=http.json('https://api.polyhaven.com/assets')
    rows=[]
    for name,a in data.items():
        if key is not None and name!=key:continue
        rows.append(item(s['id'],name,a.get('name',name),{0:'hdri',1:'texture',2:'model-3d'}.get(a.get('type'),'model-3d'),'CC0-1.0','https://polyhaven.com/license',', '.join(a.get('authors',{})),a.get('tags',[])+a.get('categories',[]),['hdr','exr'] if a.get('type')==0 else ['blend','gltf'] if a.get('type')==2 else ['png','jpg','exr'],previews=[{'url':'https://cdn.polyhaven.com/asset_img/thumbs/'+quote(name)+'.png?width=512&height=512'}],revision=a.get('files_hash','')))
    if key is not None:
        if not rows:raise ValueError('Item no longer exists at Poly Haven')
        a=rows[0];manifest=http.json('https://api.polyhaven.com/files/'+quote(key))
        def walk(x,path=(),bundle='',relative=''):
            if isinstance(x,dict):
                if isinstance(x.get('url'),str):
                    folder=bundle or '/'.join(path);filename=PurePosixPath(urlsplit(x['url']).path).name
                    a['files'].append({'url':x['url'],'filename':filename,'relative_path':relative or filename,'variant':'/'.join(path),'bundle_key':folder,'role':'dependency' if bundle else 'variant','bytes':x.get('size'),'sha256':x.get('sha256'),'md5':x.get('md5')})
                    for n,v in x.get('include',{}).items():walk(v,path+('include',n),folder,n)
                for n,v in x.items():
                    if n!='include':walk(v,path+(n,),bundle,relative)
            elif isinstance(x,list):
                for i,v in enumerate(x):walk(v,path+(str(i),),bundle,relative)
        walk(manifest)
        if len(a['files'])>2000:raise ValueError('Provider manifest budget exceeded')
        return a
    return window(rows,after,limit,f)

def ambient(http,s,f,after,limit,key=None):
    offset=int(after or 0)
    url='https://ambientcg.com/api/v2/full_json?'+('id='+quote(key)+'&include=downloadData,tagData' if key else f'limit=100&offset={offset}&include=tagData&sort=Alphabet')
    data=http.json(url);rows=[]
    for a in data.get('foundAssets',[]):
        name=a['assetId'];kind={'3DModel':'model-3d','HDRI':'hdri','Material':'material','PlainTexture':'texture','Decal':'decal','Atlas':'atlas','Terrain':'terrain','Brush':'brush'}.get(a.get('dataType'),'texture')
        record=item(s['id'],name,a.get('displayName',name),kind,'CC0-1.0','https://docs.ambientcg.com/license/','ambientCG',a.get('tags',[]),previews=[{'url':'https://ambientcg.com/get?file='+quote(name)+'_preview.jpg'}],revision=a.get('releaseDate',''))
        if key:
            def walk(x):
                if isinstance(x,dict):
                    u=x.get('downloadLink') or x.get('downloadUrl')
                    if u:record['files'].append({'url':u,'filename':x.get('fileName') or x.get('filename') or PurePosixPath(urlsplit(u).path).name,'role':'variant','bytes':x.get('size') or x.get('sizeBytes')})
                    for v in x.values():walk(v)
                elif isinstance(x,list):
                    for v in x:walk(v)
            walk(a)
            record['formats']=sorted({PurePosixPath(v['filename']).suffix.lstrip('.') for v in record['files']})
        rows.append(record)
    if key:
        if not rows:raise ValueError('Item no longer exists at ambientCG')
        return rows[0]
    # The remote page is a window, not a complete provider count.
    selected=[];consumed=0
    for a in rows:
        consumed+=1
        if matches(a,f):selected.append(a)
        if len(selected)==limit:break
    return {'items':selected,'next':str(offset+consumed) if consumed<len(rows) or len(rows)==100 else None,'total':None,'scope':'Provider page; refine source filters if this page has no matches'}

def github(http,s,f,after,limit,key=None):
    repo=s['repo'];meta=http.json('https://api.github.com/repos/'+repo)
    if meta.get('private'):raise ValueError('Source is no longer public; private repository access is not used')
    commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+quote(meta['default_branch'],safe=''))['sha']
    entries=[e for e in complete_tree(http,repo,commit,max_requests=32) if e['type']=='blob'];by_path={e['path']:e for e in entries};raw=f'https://raw.githubusercontent.com/{repo}/{commit}/'
    is_media=s['adapter']=='github-assets';rows=[];pattern=s.get('path_pattern','.*');notices={};dedications={}
    def read_notice(path):return http.text(raw+quote(path,safe='/'),256*1024)
    if is_media:
        for e in entries:
            if PurePosixPath(e['path']).name.lower() in LICENSE_NAMES and re.search(s.get('license_pattern','.*'),e['path']):notices[str(PurePosixPath(e['path']).parent)]=e
    root_notice=next((e for e in entries if '/' not in e['path'] and e['path'].lower() in LICENSE_NAMES),None)
    lic=(meta.get('license') or {}).get('spdx_id','unknown')
    variants={};candidates=entries
    if is_media:
        groups={};other=[]
        for v in entries:
            p=PurePosixPath(v['path']);ext=p.suffix.lstrip('.').lower()
            if MEDIA.get(ext) not in {'model-3d','animation-3d','scene-3d'}:other.append(v);continue
            scope=max((root for root in notices if root=='.' or v['path'].startswith(root+'/')),key=len,default='')
            logical='/'.join(part for part in p.parent.parts if part.lower() not in FORMAT_DIRS)
            groups.setdefault((scope,MEDIA[ext],logical,p.stem),[]).append(v)
        candidates=other
        for group in groups.values():
            group.sort(key=lambda v:({'glb':0,'gltf':1,'blend':2,'fbx':3,'obj':4}.get(PurePosixPath(v['path']).suffix.lstrip('.').lower(),10),v['path']))
            primary=group[0];variants[primary['path']]=group;candidates.append(primary)
    for e in sorted(candidates,key=lambda e:e['path']):
        path=e['path'];ext=PurePosixPath(path).suffix.lower().lstrip('.')
        if key is not None and path!=key and not any(v['path']==key for v in variants.get(path,[])):continue
        if key is None and path<=after:continue
        if f.get('_pack_key') and f['_pack_key']!='.' and not path.startswith(f['_pack_key']+'/'):continue
        if not re.search(pattern,path) or re.search(r'(^|/)(node_modules|vendor|\.github|tests?|__tests__|dist)(/|$)|\.(test|spec|stories|demo|d)\.(t|j)sx?$',path):continue
        if not acceptable(path):continue
        legal=root_notice;license=lic if s.get('license_scope_reviewed') else 'unknown';scope=''
        if repo=='google/fonts':
            if not path.endswith('/METADATA.pb'):continue
            family=str(PurePosixPath(path).parent);scope=family;legal=by_path.get(family+'/OFL.txt');license='OFL-1.1' if legal and path.startswith('ofl/') else 'unknown';kind='font'
        elif is_media:
            if ext not in MEDIA:continue
            scope=max((p for p in notices if p=='.' or path.startswith(p+'/')),key=len,default='')
            if not scope:continue
            legal=notices[scope]
            if scope not in dedications:dedications[scope]=read_notice(legal['path']).lower()
            text=dedications[scope]
            if any(term in text for term in ('run repository supplemental license','run projects only','personal use only','non-commercial use only','noncommercial use only')):continue
            license='CC0-1.0' if any(x in text for x in ['creativecommons.org/publicdomain/zero/1.0','cc0 1.0 universal','creative commons zero v1.0']) else 'unknown'
            if license=='unknown' and s.get('media_license_scope')=='pack-license' and 'permission is hereby granted, free of charge' in text and 'the software is provided "as is"' in text:license='MIT'
            kind=MEDIA[ext]
            if kind=='texture' and ext in {'png','jpg','jpeg','webp'} and re.search(r'(?:sprite|tileset|tilemap|pixel[-_ ]?art|2d[-_ ]?assets|characters?/[a-z])',repo+'/'+path,re.I) and not re.search(r'(?:^|/)(?:3d|textures?|materials?)(?:/|$)',path.lower()):kind='sprite'
            if kind=='texture' and s.get('image_kind') and not re.search(r'(?:^|/)(?:3d|textures?|materials?)(?:/|$)',path.lower()):kind=s['image_kind']
        else:kind=s.get('kind','ui-component')
        filename=PurePosixPath(path).name
        group=variants.get(path,[e])
        files=[{'url':raw+quote(v['path'],safe='/'),'filename':PurePosixPath(v['path']).name,'relative_path':v['path'],'sha':v['sha'],'bytes':v.get('size'),'role':'main' if v==e else 'variant'} for v in group]
        if is_media and kind in {'model-3d','animation-3d','scene-3d'}:
            parents={str(PurePosixPath(v['path']).parent) for v in group}
            dependencies=[v for v in entries if v not in group and str(PurePosixPath(v['path']).parent) in parents and PurePosixPath(v['path']).suffix.lower() in {'.bin','.mtl','.png','.jpg','.jpeg','.webp'}]
            atlases=[v for v in entries if (scope=='.' or v['path'].startswith(scope+'/')) and '/textures/' in ('/'+v['path'].lower()) and PurePosixPath(v['path']).suffix.lower() in {'.png','.jpg','.jpeg','.webp'}]
            if len(atlases)<=16:dependencies+=atlases
            for v in {v['path']:v for v in dependencies}.values():files.append({'url':raw+quote(v['path'],safe='/'),'filename':PurePosixPath(v['path']).name,'relative_path':v['path'],'sha':v['sha'],'bytes':v.get('size'),'role':'dependency'})
        if kind=='font':files=[{'url':raw+quote(v['path'],safe='/'),'filename':PurePosixPath(v['path']).name,'relative_path':v['path'],'sha':v['sha'],'bytes':v.get('size'),'role':'variant'} for v in entries if str(PurePosixPath(v['path']).parent)==family and v['path'].lower().endswith(('.ttf','.otf','.woff','.woff2'))]
        if legal:files.append({'url':raw+quote(legal['path'],safe='/'),'filename':PurePosixPath(legal['path']).name,'relative_path':legal['path'],'sha':legal['sha'],'bytes':legal.get('size'),'role':'license'})
        if is_media:
            provenance=by_path.get((scope+'/' if scope!='.' else '')+'SOURCE.md')
            if provenance:files.append({'url':raw+quote(provenance['path'],safe='/'),'filename':'SOURCE.md','relative_path':provenance['path'],'sha':provenance['sha'],'bytes':provenance.get('size'),'role':'provenance'})
        a=item(s['id'],path,filename if kind!='font' else family.split('/')[-1],kind,license,('https://github.com/'+repo+'/blob/'+commit+'/'+quote(legal['path'],safe='/')) if legal else '',repo.split('/')[0],s.get('asset_tags',s.get('tags',[]))+path.split('/'),sorted({PurePosixPath(v['path']).suffix.lstrip('.').lower() for v in group}) if kind!='font' else sorted({PurePosixPath(v['filename']).suffix.lstrip('.') for v in files if v['role']!='license'}),files=files,pack=scope,revision=hashlib.sha256(''.join(v['sha'] for v in group).encode()).hexdigest() if len(group)>1 else e['sha'],previews=[{'url':raw+quote(path,safe='/')}] if ext in {'png','jpg','jpeg','webp','svg'} else [])
        a['platforms']=s.get('platforms',a['platforms']);a['software_only']=not is_media and kind!='font'
        # License checks are deferred until a matching page candidate, not all files.
        if matches(a,f):rows.append(a)
        if key is None and len(rows)>=limit+1:break
    if key is not None:
        if not rows:raise ValueError('Item is missing, out of scope, or no longer rights-eligible')
        return rows[0]
    return window(rows,after,limit,f)

def codrops(http,s,f,after,limit,key=None):
    if f.get('_pack_key'):
        base=codrops(http,s,{'mode':'all'},'',1,key=f['_pack_key']);rows=[]
        for original in base['files']:
            if original.get('role')=='license':continue
            record=dict(base);record['key']=base['key']+'|'+original['relative_path'];record['title']=original['filename'];record['kind']='shader' if original['filename'].endswith(('.glsl','.frag','.vert')) else 'template' if original['filename'].endswith('.html') else 'ui-component';record['files']=[{**v,'role':'main' if v==original else v['role']} for v in base['files']];record['formats']=[PurePosixPath(original['filename']).suffix.lstrip('.')];record['revision']=original['sha'];record['upstream_path']=original['relative_path'];record['repo']='codrops/'+base['key'];rows.append(record)
        return window(rows,after,limit,f)
    if key:
        pack,_,member=key.partition('|');repo='codrops/'+pack;meta=http.json('https://api.github.com/repos/'+repo)
        if (meta.get('license') or {}).get('spdx_id')!='MIT':raise ValueError('Current Codrops code license is not verified MIT')
        commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+quote(meta['default_branch'],safe=''))['sha'];entries=complete_tree(http,repo,commit,max_requests=12);selected=code_entries(entries)
        notice=next((e for e in entries if e['path'].upper() in {'LICENSE','LICENSE.TXT','LICENSE.MD'}),None)
        if not notice or not selected:raise ValueError('No original code pack with a verified notice')
        raw=f'https://raw.githubusercontent.com/{repo}/{commit}/';text=http.text(raw+quote(notice['path'],safe='/'),256*1024)
        if 'permission is hereby granted, free of charge' not in text.lower():raise ValueError('MIT notice is missing')
        selected.sort(key=lambda e:(e['path']!='index.html',e['path']));files=[{'url':raw+quote(e['path'],safe='/'),'filename':PurePosixPath(e['path']).name,'relative_path':e['path'],'sha':e['sha'],'bytes':e.get('size'),'role':'license' if e==notice else 'main' if e==selected[0] else 'dependency'} for e in selected+[notice]]
        result=item(s['id'],key,meta['name'],'template' if re.search('template|layout|portfolio|website',meta['name'],re.I) else 'motion','MIT','https://github.com/'+repo+'/blob/'+commit+'/'+notice['path'],'Codrops',['Codrops',meta.get('description') or ''],sorted({PurePosixPath(v['filename']).suffix.lstrip('.') for v in files}),files=files,description='Original code only; fonts, images and vendor libraries have independent rights.',pack=pack,revision=commit)
        result['software_only']=True
        if member:
            selected_file=next((v for v in files if v['relative_path']==member and v['role']!='license'),None)
            if not selected_file:raise ValueError('Pack source member no longer exists or is outside its original-code scope')
            result.update(title=selected_file['filename'],kind='shader' if member.endswith(('.frag','.vert','.glsl')) else 'template' if member.endswith('.html') else 'ui-component',formats=[PurePosixPath(member).suffix.lstrip('.')],revision=selected_file['sha'],upstream_path=member,repo=repo,files=[{**v,'role':'main' if v==selected_file else 'license' if v['role']=='license' else 'dependency'} for v in files])
        return result
    offset=int(after or 0);page=offset//100+1;start=offset%100;data=http.json(f'https://api.github.com/orgs/codrops/repos?type=public&per_page=100&page={page}')
    rows=[];consumed=start
    for a in data[start:]:
        consumed+=1
        if not a.get('fork') and not a.get('private') and (a.get('license') or {}).get('spdx_id')=='MIT':
            candidate=item(s['id'],a['name'],a['name'],'template' if re.search('template|layout|portfolio|website',a['name'],re.I) else 'motion','MIT','https://github.com/'+a['full_name']+'/blob/'+a['default_branch']+'/LICENSE','Codrops',[a.get('description') or ''],['html','js','css'],pack=a['name'],revision=a.get('pushed_at',''))
            candidate['software_only']=True
            if matches(candidate,f):rows.append(candidate)
        if len(rows)==limit:break
    return {'items':rows,'next':str((page-1)*100+consumed) if consumed<len(data) or len(data)==100 else None,'total':None,'scope':'Current organization page; code notices revalidated when opening a pack'}

def aceternity(http,s,f,after,limit,key=None):
    data=http.json('https://ui.aceternity.com/registry/registry.json')
    rows=[item(s['id'],a['name'],a.get('title',a['name'].replace('-',' ')),'ui-component','unknown','https://ui.aceternity.com/licence','Aceternity',tags=['react','motion','free-registry','licence-unresolved'],formats=['tsx'],description='Public free registry entry. Original source access is withheld until applicable item reuse rights are verified.') for a in data.get('items',[]) if a.get('name')]
    if key is not None:
        a=next((a for a in rows if a['key']==key),None)
        if not a:raise ValueError('Component no longer appears in the public free registry')
        return a
    return window(rows,after,limit,f)

from .live_web import public_web
from .live_blendkit import blendkit
from .live_media import fuel,fsd50k,blender_demos,khronos
from .live_packs import kenney,quaternius
from .live_luts import luts
from .live_icons import icons
from .live_catalogs import openverse,commons,artic
from .live_services import npm_package
from .live_discovery import github_current
from .live_public_assets import lazytextures,opengameart,internet_archive
def repository(http,s,f,after,limit,key=None):
    # Revalidate current per-pack CC0 media scopes or permissive software rights.
    media=f.get('kind') in (set(MEDIA.values())-{'shader'}) or f.get('section','').startswith(('three-d','two-d','surfaces','lighting','audio'))
    config={**s,'adapter':'github-assets' if media else 'github-tree','kind':'ui-component','license_scope_reviewed':not media,'path_pattern':r'\.(?:tsx?|jsx?|css|scss|html|vue|svelte|glsl|frag|vert|swift|dart|xaml|py|gd)$' if not media else r'.*'}
    if not media:
        meta=http.json('https://api.github.com/repos/'+s['repo']);license=(meta.get('license') or {}).get('spdx_id')
        if license not in LICENSES:config['license_scope_reviewed']=False
    return github(http,config,f,after,limit,key)

ADAPTERS={'polyhaven':polyhaven,'ambientcg':ambient,'github-tree':github,'github-assets':github,'codrops':codrops,'aceternity':aceternity,'public-web':public_web,'blendkit':blendkit,'fuel':fuel,'fsd50k':fsd50k,'blender-demos':blender_demos,'khronos':khronos,'kenney-packs':kenney,'quaternius-live':quaternius,'lut-manifest':luts,'iconify':icons,'github-repository':repository}
ADAPTERS.update({'openverse':openverse,'commons':commons,'artic':artic})
ADAPTERS['npm-package']=npm_package
ADAPTERS['github-current']=github_current
ADAPTERS.update({'lazytextures':lazytextures,'opengameart':opengameart,'internet-archive':internet_archive})
from .live_collections import descriptor_catalog,pack_library,open_asset_archive
ADAPTERS.update({'asset-descriptor-catalog':descriptor_catalog,'github-pack-library':pack_library,'open-assets-catalog':open_asset_archive})
from .live_online import poly_pizza,texturecan,museum,incompetech
ADAPTERS.update({'poly-pizza':poly_pizza,'texturecan':texturecan,'met-open-access':museum,'cleveland-open-access':museum,'incompetech':incompetech})

class Providers:
    def __init__(self,http,sources):self.http=http;self.sources=sources
    def config(self,sid):
        source=self.sources[sid];canonical=self.sources.get(source.get('live_alias_of'),{})
        # An older generic connection must not bypass a specialized collection
        # licence/tree contract. Other intentionally different repo scopes keep
        # their own filters and are not widened through this rule.
        return canonical if canonical.get('live_adapter',canonical.get('adapter')) in {'github-pack-library','asset-descriptor-catalog','open-assets-catalog'} else source
    def page(self,sid,filters,after='',limit=20):
        s=self.config(sid);adapter=s.get('live_adapter',s['adapter'])
        if adapter not in ADAPTERS:raise ValueError(s.get('live_reason','No permitted live inventory connector implemented for this source'))
        return ADAPTERS[adapter](self.http,s,filters,after,limit)
    def get(self,sid,key):
        s=self.config(sid);adapter=s.get('live_adapter',s['adapter'])
        if adapter not in ADAPTERS:raise ValueError(s.get('live_reason','No live item connector'))
        filters={'mode':'all'}
        if adapter=='github-repository' and PurePosixPath(key).suffix.lstrip('.').lower() in MEDIA and MEDIA[PurePosixPath(key).suffix.lstrip('.').lower()]!='shader':filters['kind']=MEDIA[PurePosixPath(key).suffix.lstrip('.').lower()]
        return ADAPTERS[adapter](self.http,s,filters,'',1,key=key)
