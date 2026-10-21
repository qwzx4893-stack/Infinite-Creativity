"""Author-published public registries, not scraped marketplace collections."""
import hashlib,json,re
from pathlib import PurePosixPath
from urllib.parse import quote
from .policy import acceptable,review_terms

CODE={'.tsx','.jsx','.ts','.js','.css','.scss','.json'}
KINDS={'registry:ui','registry:component','registry:block','registry:page'}

def safe_path(path):
    if not isinstance(path,str) or not path or len(path)>500 or path.startswith('/') or '\\' in path or ':' in path or '..' in PurePosixPath(path).parts:
        raise ValueError('Unsafe registry member path')
    return str(PurePosixPath(path))

def index(http,source):
    indexes=source.get('registry_indexes') or [{'url':source['registry_index']}]
    if len(indexes)>8:raise ValueError('Too many registry index scopes')
    result={}
    for descriptor in indexes:
        data=http.json(descriptor['url']);rows=data.get('items',[])
        if not isinstance(rows,list) or len(rows)+len(result)>4000:raise ValueError('Registry index exceeds bounded navigation budget')
        for v in rows:
            if not isinstance(v,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',str(v.get('name',''))):continue
            if v['name'] in result:raise ValueError('Ambiguous duplicate name across author registry indexes')
            result[v['name']]={**v,**({'_source_root':safe_path(descriptor['root'])} if descriptor.get('root') else {})}
    return result

def rights(http,source):
    repo=source['repo'];meta=http.json('https://api.github.com/repos/'+repo)
    if meta.get('private') or (meta.get('license') or {}).get('spdx_id')!='MIT':raise ValueError('Current author repository is not public MIT source')
    commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+quote(meta['default_branch'],safe=''))['sha']
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid author revision')
    path=source.get('registry_license','LICENSE');url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+path
    body=http.read(url,256*1024);text=body.decode('utf-8-sig').lower()
    if 'permission is hereby granted, free of charge' not in text or any(x in text for x in ('commons clause','personal use only','non-commercial use only')):raise ValueError('Current registry code notice is not the reviewed MIT contract')
    return {'url':url,'filename':'LICENSE','relative_path':'__licenses__/'+source['id'].replace(':','-')+'/LICENSE',
            'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'role':'license'},'https://github.com/'+repo+'/blob/'+commit+'/'+path

def public_registry(http,source,filters,after,limit,key=None):
    from .live_providers import item,matches
    from .live import seal
    config=__import__('infinite_creativity.live',fromlist=['source_configs']).source_configs()
    trusted={s['id']:s for s in config.values() if s.get('adapter')=='public-registry'}
    trusted[source['id']]=source
    indexes={};notices={}
    def catalog(s):
        if s['id'] not in indexes:indexes[s['id']]=index(http,s)
        return indexes[s['id']]
    available=catalog(source);groups={}
    for name,row in available.items():
        if row.get('type') not in KINDS or row.get('premium') or row.get('requiresAuth') or row.get('access') in {'paid','private'}:continue
        group=re.sub(r'-(?:JS|TS)-(?:CSS|TW)$','',name) if source.get('group_variants') else name
        groups.setdefault(group,[]).append(name)
    def preferred(names):return sorted(names,key=lambda n:(not n.endswith('-TS-TW'),not n.endswith('-TS-CSS'),n))
    if key:
        group,separator,variant=key.partition('|')
        if group not in groups or separator and variant not in groups[group]:raise ValueError('Component/variant is absent from its current public author registry')
        candidates=[(group,variant or preferred(groups[group])[0])]
    else:
        candidates=[]
        for group,names in sorted(groups.items()):
            if group<=after:continue
            row=available[preferred(names)[0]]
            preview=item(source['id'],group,row.get('title') or group,'template' if row.get('type') in {'registry:block','registry:page'} else 'ui-component','MIT','https://github.com/'+source['repo'],tags=[*source.get('asset_tags',[]),group],description=row.get('description') or '')
            if matches(preview,{k:v for k,v in filters.items() if k not in {'format','platform','style'}}):candidates.append((group,preferred(names)[0]))
            if len(candidates)>=min(limit,6)+1:break
    rows=[];errors=[]
    for group,name in candidates[:min(limit,6)]:
        try:
            nodes=[];visited=set();file_map={};dependencies=set();license_urls={};payloads=[]
            def resolve_dependency(s,dependency):
                if not isinstance(dependency,str) or len(dependency)>500:raise ValueError('Invalid registry dependency')
                if dependency.startswith('https://'):
                    for other in trusted.values():
                        if not other.get('registry_item'):continue
                        before,after_name=other['registry_item'].split('{name}')
                        if dependency.startswith(before) and dependency.endswith(after_name):
                            dependency_name=dependency[len(before):len(dependency)-len(after_name)] if after_name else dependency[len(before):]
                            if re.fullmatch('[A-Za-z0-9_-]{1,150}',dependency_name):return other,dependency_name
                    raise ValueError('Dependency is not an independently licensed configured public registry')
                if dependency.startswith('@'):
                    namespace,_,dependency_name=dependency.partition('/')
                    other=next((v for v in trusted.values() if v.get('registry_namespace')==namespace),None)
                    if other and dependency_name in catalog(other):return other,dependency_name
                    raise ValueError('Unknown registry dependency namespace')
                if dependency in catalog(s):return s,dependency
                fallback=next((v for v in trusted.values() if v.get('registry_namespace')=='@shadcn'),None)
                if fallback and dependency in catalog(fallback):return fallback,dependency
                raise ValueError('Registry dependency lacks a current licensed member')
            def collect(s,n):
                identity=(s['id'],n)
                if identity in visited:return
                if len(visited)>=12:raise ValueError('Registry dependency graph exceeds twelve items')
                if n not in catalog(s):raise ValueError('Component is no longer indexed by its author')
                visited.add(identity)
                if s['id'] not in notices:notices[s['id']]=rights(http,s)
                legal,legal_url=notices[s['id']];license_urls[s['id']]=legal_url
                repository_files=bool(s.get('registry_repository_files'))
                if repository_files:
                    # The author also publishes this registry's original code
                    # in GitHub. Use its own pinned source, never marketplace
                    # curation or an authenticated registry endpoint.
                    payload=dict(catalog(s)[n]);endpoint=''
                else:
                    endpoint=s['registry_item'].replace('{name}',quote(n,safe=''));payload=http.json(endpoint)
                if payload.get('name')!=n or payload.get('premium') or payload.get('requiresAuth') or payload.get('access') in {'paid','private'} or payload.get('license','MIT')!='MIT':raise ValueError('Public component rights/name/access contract changed')
                payloads.append(payload);nodes.append({'source':s['id'],'name':n,'license_url':legal_url})
                if n!='index' and catalog(s).get('index',{}).get('type')=='registry:style':collect(s,'index')
                for dependency in payload.get('registryDependencies',[]):
                    other,dependency_name=resolve_dependency(s,dependency);collect(other,dependency_name)
                dependencies.update(payload.get('dependencies',[]))
                member_paths=set()
                for f in payload.get('files',[]):
                    path=safe_path(f.get('path',''))
                    if repository_files:path=safe_path(str(PurePosixPath(payload['_source_root'])/path))
                    suffix=PurePosixPath(path).suffix.lower()
                    if path in member_paths:raise ValueError('Duplicate member path in registry payload')
                    member_paths.add(path)
                    if suffix not in CODE or re.search(r'(^|/)(?:node_modules|vendor|\.github)(/|$)',path):raise ValueError('Non-code registry member requires separate original-media rights/review')
                    original_url=None
                    if repository_files:
                        revision=legal['url'].split('/')[5]
                        original_url='https://raw.githubusercontent.com/'+s['repo']+'/'+revision+'/'+quote(path,safe='/')
                        text=http.read(original_url,2*1024*1024).decode('utf-8-sig')
                    else:text=f.get('content')
                    if not isinstance(text,str) or not text.strip() or len(text.encode())>2*1024*1024:raise ValueError('Registry original is missing or exceeds the source-text budget')
                    if not acceptable(text) or review_terms(text):raise ValueError('Registry original source violates sexual/suggestive content policy')
                    body=text.encode();digest=hashlib.sha256(body).hexdigest()
                    if path in file_map and file_map[path]['sha256']!=digest:raise ValueError('Conflicting dependency destinations in registry bundle')
                    file_map[path]={'url':original_url or endpoint,'filename':PurePosixPath(path).name,'relative_path':path,**({} if repository_files else {'json_content_path':f['path']}),
                                    'role':'dependency','sha256':digest,'bytes':len(body),'_root':identity==(source['id'],name),'_registry_type':f.get('type'),'_text':text}
                    if len(file_map)>40 or sum(v['bytes'] for v in file_map.values())>8*1024*1024:raise ValueError('Registry source bundle exceeds bounded file/byte budget')
            collect(source,name)
            if not file_map:raise ValueError('Registry component has no public original source')
            roots=[v for v in file_map.values() if v['_root']]
            if not roots:raise ValueError('Root component has no distinct original member')
            main=min(roots,key=lambda v:(PurePosixPath(v['filename']).suffix not in {'.tsx','.jsx'},v['_registry_type'] not in KINDS,-v['bytes']))
            main['role']='main'
            files=[{k:value for k,value in f.items() if not k.startswith('_')} for f in file_map.values()]+[notices[sid][0] for sid in license_urls]
            current=next(p for p in payloads if p.get('name')==name);listing=available[name]
            title=current.get('title') or listing.get('title') or group
            a=item(source['id'],group+('|'+name if key and '|' in key else ''),title,'template' if listing.get('type') in {'registry:block','registry:page'} else 'ui-component',
                   'MIT',license_urls[source['id']],str(current.get('author') or source['repo'].split('/')[0]),[*source.get('asset_tags',[]),group],
                   sorted({PurePosixPath(v['filename']).suffix[1:] for v in file_map.values()}),files=files,
                   description=current.get('description') or listing.get('description') or '',pack=source['id'],
                   revision=hashlib.sha256(json.dumps([(v['relative_path'],v['sha256']) for v in files],sort_keys=True).encode()).hexdigest())
            a['software_only']=True;a['origin_identity']='author-registry:'+source['repo']+':'+group
            a['features']={'registry_dependencies':nodes,'npm_dependencies':sorted(dependencies),
                           'implementation':name,'implementation_variants':[{'name':v,'asset_id':seal('asset',{'source':source['id'],'key':group+'|'+v})} for v in preferred(groups[group])],
                           'registry_configuration':[{"name":p['name'],**{k:p[k] for k in ('css','cssVars','tailwind','devDependencies') if k in p}} for p in payloads if any(k in p for k in ('css','cssVars','tailwind','devDependencies'))],
                           'quality_evidence':{'provider':source['repo'],'basis':'Author-published public component bundle, current MIT notices and complete bounded registry dependency resolution.','visual_design':'unverified; source code is not a rendered UI.'}}
            a['reuse_scope']='Independent author-published MIT source and its scoped MIT dependencies; preserve all included notices. Marketplace curation, screenshots, paid items and embedded remote media are outside this grant. No code or installation scripts are executed.'
            from .live_quality import inspect_source_bundle
            a['features']['source_quality']=inspect_source_bundle(file_map,dependencies)
            if a['features']['source_quality']['state']=='rejected':raise ValueError('Component source failed automatic syntax/completeness checks')
            if key or matches(a,filters):rows.append(a)
        except Exception as e:
            if key:raise
            errors.append({'key':group,'reason':str(e)[:240]})
    if key:
        if not rows:raise ValueError('Current registry component is not reusable/reviewable')
        return rows[0]
    return {'items':rows,'next':candidates[min(limit,6)-1][0] if len(candidates)>min(limit,6) else None,'total':None,'item_errors':errors,
            'catalog':{'logical_components':len(groups),'implementation_variants':sum(map(len,groups.values())),'admitted_unique_assets':None,'count_scope':'Fresh author index; implementations are grouped, not counted as separate creative designs.'},
            'scope':'Public author registry and exact licensed dependency bundles, not the 21st marketplace. Current original source is fetched each RPC; no registry payload or catalogue is saved.'}
