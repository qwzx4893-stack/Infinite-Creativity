"""No-account first-party art, model, material and music inventories.

Only public JSON/HTML is read. No site script, login flow, token endpoint,
advertisement inventory or premium download is executed or followed.
"""
import hashlib,html,json,re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote,urlencode,urljoin,urlsplit
from .policy import acceptable,review_terms,normalize_query
from .live_catalogs import cc_license,plain

def revision(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Markup(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.links=[];self.images=[];self.scripts=[];self._script=False;self._text=[];self.title=[];self._title=False
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='a' and d.get('href'):self.links.append(d['href'])
        if tag=='img' and d.get('src'):self.images.append(d['src'])
        if tag=='script' and not d.get('src'):self._script=True;self._text=[]
        if tag=='title':self._title=True
    def handle_data(self,value):
        if self._script:self._text.append(value)
        if self._title:self.title.append(value)
    def handle_endtag(self,tag):
        if tag=='script' and self._script:self.scripts.append(''.join(self._text));self._script=False
        if tag=='title':self._title=False

def markup(body):
    p=Markup();p.feed(body);return p

def public_file(http,url,filename,role='main',**extra):
    if urlsplit(url).scheme!='https':raise ValueError('Original must use public HTTPS')
    http.approve_content(url)
    return {'url':url,'filename':filename,'relative_path':filename,'role':role,**extra}

def poly_pizza(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    def model(public_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',public_id):raise ValueError('Invalid public model locator')
        page='https://poly.pizza/m/'+public_id;body=http.text(page);parsed=markup(body);prefix='window.__SERVER_APP_STATE__ ='
        script=next((v.strip()[len(prefix):].strip() for v in parsed.scripts if v.strip().startswith(prefix)),None)
        if not script:raise ValueError('Public model descriptor is unavailable')
        # The public SSR envelope includes bare undefined values. Normalize
        # those tokens outside strings only; never evaluate JavaScript.
        script=re.sub(r'"(?:\\.|[^"\\])*"|\bundefined\b',lambda m:'null' if m[0]=='undefined' else m[0],script)
        state,end=json.JSONDecoder().raw_decode(script)
        if script[end:].strip() not in {'',';'}:raise ValueError('Unexpected public descriptor suffix')
        d=state.get('initialData',{}).get('model',{});label=str(d.get('Licence','')).upper().replace(' ','-')
        licences={'CC0-1.0':('CC0-1.0','https://creativecommons.org/publicdomain/zero/1.0/'),'CC-BY-3.0':('CC-BY-3.0','https://creativecommons.org/licenses/by/3.0/'),'CC-BY-4.0':('CC-BY-4.0','https://creativecommons.org/licenses/by/4.0/')}
        if label not in licences or d.get('PublicID')!=public_id:raise ValueError('Model has no supported current per-item free licence')
        resource=d.get('ResourceID','')
        if not re.fullmatch('[a-f0-9-]{36}',resource):raise ValueError('Unsupported public model resource identity')
        url='https://static.poly.pizza/'+resource+'.glb'
        if url not in body:raise ValueError('Original is not exposed in the current public model presentation')
        creator=d.get('Creator',{});author=creator.get('Username','');lic,uri=licences[label]
        if not author:raise ValueError('Current model creator credit unavailable')
        stable={k:d.get(k) for k in ('Title','ResourceID','PublicID','UploadDate','Licence','Creator','Tags','Animated')}
        # Popularity counters and profile-picture changes are not revisions of
        # model rights/content. Exact delivery still validates original bytes.
        stable['Creator']={'Username':author}
        a=item(s['id'],public_id,d.get('Title',public_id),'model-3d',lic,uri,author,d.get('Tags',[])+['low-poly'],['glb'],files=[public_file(http,url,public_id+'.glb')],revision=revision(stable))
        a['features']={'declared_technical':{'triangleCount':d.get('Tris'),'animated':bool(d.get('Animated'))},'attribution':d.get('Title',public_id)+' by '+author+' — '+page+' — '+uri,'origin_page':page,'evidence_scope':'Public per-model licence and renderer GLB; no premium/file-token endpoint used.'}
        a['origin_url']=page
        return a
    if key is not None:return model(key)
    state=json.loads(after) if after else {'page':1,'skip':0};query=normalize_query(f.get('query','')).strip();endpoint='/api/search/'+quote(query,safe='') if query else '/api/explore'
    data=http.json('https://poly.pizza'+endpoint+'?'+urlencode({'Page':state['page']}));candidates=data.get('results',[])
    if not isinstance(candidates,list) or len(candidates)>128:raise ValueError('Unexpected public model page shape')
    rows=[];errors=[];position=state['skip']
    for d in candidates[position:]:
        position+=1
        if not isinstance(d,dict) or not d.get('publicID') or not acceptable(str(d.get('title',''))) or review_terms(str(d.get('title',''))):continue
        try:
            a=model(d['publicID'])
            if matches(a,{**f,'query':''}):rows.append(a)
        except ValueError as e:errors.append({'item':d.get('publicID'),'reason':str(e)[:150]})
        if len(rows)>=limit:break
    count=data.get('count');more=bool(candidates) and (not isinstance(count,int) or state['page']*32<count)
    nxt={'page':state['page'],'skip':position} if position<len(candidates) else {'page':state['page']+1,'skip':0} if more else None
    return {'items':rows,'next':json.dumps(nxt) if nxt else None,'scope':'Current public free-model page; paid asset advertisements are excluded. Counts are upstream search scope only.','item_errors':errors}

def texturecan(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    from .live_public_assets import zip_members
    rights=http.text('https://www.texturecan.com/terms/')
    if not re.search(r'creativecommons.org/publicdomain/zero/1.0|Creative Commons CC0',rights,re.I):raise ValueError('Current material CC0 dedication unavailable')
    def material(identifier):
        if not re.fullmatch(r'\d{1,8}',identifier):raise ValueError('Invalid public material locator')
        body=http.text('https://www.texturecan.com/details/'+identifier+'/');p=markup(body)
        files=[]
        for path in p.links:
            if re.fullmatch(r'/downloads/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.zip',path):
                resolution=re.search(r'_(\d+)k_',path,re.I);files.append(public_file(http,'https://www.texturecan.com'+path,PurePosixPath(path).name,'variant',variant=(resolution[1]+'k') if resolution else ''))
        if not files:raise ValueError('No public free original pack in this current material page')
        files.sort(key=lambda x:int(x['variant'][:-1]) if x['variant'] else 999)
        files[0]['role']='main';previews=[{'url':'https://www.texturecan.com'+p} for p in p.images if re.fullmatch(r'/img/textures/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+_plane_\d+\.png',p)]
        for preview in previews:http.approve_content(preview['url'])
        title=plain(' '.join(p.title).split('|')[0]).strip();a=item(s['id'],identifier,title,'material','CC0-1.0','https://www.texturecan.com/terms/','TextureCan',['PBR',title],['zip'],files,previews,pack=identifier,revision=revision({'files':files,'title':title,'rights':rights}))
        a['features']={'pack_scope':'Public resolution archives; get_library_pack lists actual maps. A cover never licenses unseen content through the media guard.'};a['original_access']='archive-members-require-review'
        return a
    pack=f.get('_pack_key') or (key.split('|',1)[0] if key else '')
    if pack:
        parent=material(pack)
        if key and '|' not in key:return parent
        archive=next((a for a in parent['files'] if not key or key.split('|',2)[1]==a['filename']),None)
        if not archive:raise ValueError('Current resolution archive changed')
        return zip_members(http,s,parent,archive,f,after,limit,key)
    state=json.loads(after) if after else {'page':1,'skip':0};query=normalize_query(f.get('query','')).strip();stem='/search/'+quote(query,safe='')+'/' if query else '/category/New/'
    body=http.text('https://www.texturecan.com'+stem+(str(state['page'])+'/' if state['page']>1 else ''));p=markup(body)
    identifiers=list(dict.fromkeys(re.match(r'/details/(\d+)/$',v)[1] for v in p.links if re.fullmatch(r'/details/\d+/',v)));rows=[];errors=[];position=state['skip']
    for identifier in identifiers[position:]:
        position+=1
        try:
            a=material(identifier)
            if matches(a,{**f,'query':''}):rows.append(a)
        except ValueError as e:errors.append({'item':identifier,'reason':str(e)[:150]})
        if len(rows)>=limit:break
    next_page=stem+str(state['page']+1)+'/'
    nxt={'page':state['page'],'skip':position} if position<len(identifiers) else {'page':state['page']+1,'skip':0} if next_page in p.links else None
    return {'items':rows,'next':json.dumps(nxt) if nxt else None,'scope':'Current CC0 material packs; resolution variants and actual ZIP member maps remain internal.','item_errors':errors}

def museum(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    met=s['adapter']=='met-open-access';offset=int(after or 0);query=normalize_query(f.get('query','')) or '*';base='https://collectionapi.metmuseum.org/public/collection/' if met else 'https://openaccess-api.clevelandart.org/api/artworks/'
    if key and not re.fullmatch(r'\d{1,12}',key):raise ValueError('Invalid collection object locator')
    if met:
        page=http.json(base+'v1.1/search?'+urlencode({'hasImages':'true','q':query,'offset':offset,'limit':max(limit,8)})) if not key else None
        records=[http.json(base+'v1/objects/'+key)] if key else page.get('objectIDs',[])
    else:
        page=http.json(base+key) if key else http.json(base+'?'+urlencode({'cc0':'','has_image':1,'q':query,'skip':offset,'limit':max(limit,8)}));records=page.get('data',[])
        if isinstance(records,dict):records=[records]
    rows=[];consumed=0
    for record in records:
        consumed+=1;d=http.json(base+'v1/objects/'+str(record)) if met and not isinstance(record,dict) else record
        identifier=str(d.get('objectID') if met else d.get('id'))
        if key and identifier!=key:raise ValueError('Current object identity differs from the selected locator')
        title=plain(d.get('title',''));tags=[str(v.get('term','')) for v in (d.get('tags') or []) if isinstance(v,dict)] if met else [str(d.get(k) or '') for k in ('type','technique','culture')]
        if not acceptable(title+' '+' '.join(tags)) or review_terms(title+' '+' '.join(tags)):continue
        if met:
            if d.get('isPublicDomain') is not True or not d.get('primaryImage'):continue
            urls=[d['primaryImage']]+d.get('additionalImages',[])[:8];author=d.get('artistDisplayName','');rights='https://www.metmuseum.org/policies/image-resources';preview=d.get('primaryImageSmall') or urls[0];description=d.get('medium','')+' '+d.get('objectDate','')
        else:
            if d.get('share_license_status')!='CC0':continue
            images=d.get('images',{});urls=[images[k]['url'] for k in ('web','print','full') if isinstance(images.get(k),dict) and images[k].get('url')];author='; '.join(v.get('description','') for v in d.get('creators',[]));rights='https://www.clevelandart.org/open-access';preview=urls[0] if urls else '';description=d.get('technique','')+' '+(d.get('creation_date') or '')
        if not urls:continue
        files=[public_file(http,url,identifier+'-'+str(i)+(PurePosixPath(urlsplit(url).path).suffix or '.jpg'),'main' if i==0 else 'variant') for i,url in enumerate(dict.fromkeys(urls))]
        http.approve_content(preview);a=item(s['id'],identifier,title,'illustration','CC0-1.0',rights,author,tags,[PurePosixPath(v['filename']).suffix.lstrip('.').lower() for v in files],files,[{'url':preview}],description,revision=revision({'id':identifier,'rights':rights,'files':files,'title':title,'author':author}))
        a['features']={'origin_page':d.get('objectURL') if met else d.get('url'),'attribution':d.get('creditLine','') if met else d.get('creditline',''),'evidence_scope':'Current object-level Public Domain/CC0 designation; original variants are individually screened at delivery.'}
        if key or matches(a,{**f,'query':''}):rows.append(a)
        if len(rows)>=limit:break
    if key:
        if not rows:raise ValueError('Current object has no eligible public-domain image')
        return rows[0]
    total=page.get('total') if met else page.get('info',{}).get('total')
    more=consumed<len(records) or bool(records) and (not isinstance(total,int) or offset+consumed<total)
    return {'items':rows,'next':str(offset+consumed) if more else None,'scope':'Current object-level CC0 images; catalogue metadata counts are not admitted image counts.'}


def incompetech(http,s,f,after,limit,key=None):
    from .live_providers import item,matches,window
    base='https://incompetech.com/music/royalty-free/';records=http.json(base+'pieces.json')
    if not isinstance(records,list) or len(records)>10000:raise ValueError('Unexpected current music catalogue shape')
    rows=[]
    for d in sorted(records,key=lambda d:str(d.get('isrc',''))):
        identifier=str(d.get('isrc',''))
        if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}\d{7}',identifier) or key is not None and identifier!=key or key is None and identifier<=after:continue
        if f.get('_pack_key') and str(d.get('collection',''))!=f['_pack_key']:continue
        filename=d.get('filename','')
        if not isinstance(filename,str) or PurePosixPath(filename).name!=filename or '\\' in filename or ':' in filename or not filename.lower().endswith('.mp3'):continue
        title=plain(d.get('title',''));tags=['music',plain(d.get('feel','')),plain(d.get('instruments',''))];uri='https://creativecommons.org/licenses/by/4.0/'
        a=item(s['id'],identifier,title,'audio','CC-BY-4.0',uri,'Kevin MacLeod',tags,['mp3'],description=plain(d.get('description','')),pack=str(d.get('collection','')),revision=revision(d))
        if key is None and not matches(a,f):continue
        # This is the current public player's per-track licence and explicit
        # filename->MP3 route, not an assumption based on an old FAQ alone.
        page=base+'index.html?'+urlencode({'isrc':identifier});body=http.text(page)
        if not re.search(r'https?://creativecommons.org/licenses/by/4\.0/?',body) or '/music/royalty-free/mp3-royaltyfree/' not in body:raise ValueError('Current public music player licence/download contract changed')
        a['files']=[public_file(http,base+'mp3-royaltyfree/'+quote(filename,safe=''),filename)]
        duration=str(d.get('length',''));parts=duration.split(':');seconds=sum(int(v)*60**i for i,v in enumerate(reversed(parts))) if len(parts)==3 and all(v.isdigit() for v in parts) else None
        a['features']={'attribution':'"'+title+'" Kevin MacLeod (incompetech.com), licensed under Creative Commons BY 4.0: '+uri,'origin_page':page,'declared_technical':{'duration':seconds,'bpm':d.get('bpm')},'instruments':d.get('instruments'),'moods':d.get('feel'),'collection_id':d.get('collection'),'evidence_scope':'Current first-party catalogue, per-track free CC BY 4.0 player and public MP3. Paid attribution-free licences are excluded.'};a['origin_url']=page
        rows.append(a)
        if key is None and len(rows)>limit:break
    if key is not None:
        if not rows:raise ValueError('Current free track removed, unsupported or no longer in this catalogue')
        return rows[0]
    return window(rows,after,limit,f)
