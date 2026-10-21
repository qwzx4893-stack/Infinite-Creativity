"""Public, no-account original asset inventories. No saved records or media."""
import hashlib
import html
import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urljoin, urlsplit
from .asset_adapters import MEDIA
from .live_catalogs import cc_license, plain
from .policy import LICENSES, acceptable, review_terms


def scoped_url(http, base, path):
    url=urljoin(base,path)
    if urlsplit(url).netloc!=urlsplit(base).netloc:raise ValueError('Asset path leaves its public provider')
    http.approve_content(url)
    return url


def lazytextures(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    base='https://lazytextures.net:3000';types={'models':'model-3d','materials':'material','hdris':'hdri','textures':'texture','other':'volume-3d'}
    media=s['media'];offset=int(after or 0)
    if key:
        if '/' not in key or key.split('/',1)[0]!=media:raise ValueError('Invalid material/model locator')
        name=key.split('/',1)[1]
        d=http.json(base+'/previews'+{'models':'Models','materials':'Materials','hdris':'HDRIs','textures':'Textures','other':'Other'}[media])
        raw=d.get('Preview'+{'models':'Models','materials':'Materials','hdris':'HDRIs','textures':'Textures','other':'Other'}[media],d.get('data',[]))
        raw=[v for v in raw if v.get('name')==name]
    elif f.get('query'):
        d=http.json(base+'/'+media+'/Search?'+urlencode({'q':f['query'],'offset':offset,'limit':max(10,limit)}));raw=d.get('results',d.get('data',[]))
    else:
        d=http.json(base+'/previews-paginated/'+media+'?'+urlencode({'offset':offset,'limit':max(10,limit),'sort':'name-asc'}));raw=d.get('data',[])
    rows=[];consumed=0
    for v in raw:
        consumed+=1;name=v['name'];info=None;originals=[]
        if key:
            # The public /Asset route currently returns HTTP 500. The official
            # inventory also supplies a public Infos.json file with its manifest.
            path=(v.get('infosFile') or {}).get('path')
            if not path:raise ValueError('Public original manifest is unavailable')
            info=http.json(scoped_url(http,base,path))
            def walk(x,resolution='',role='variant'):
                if isinstance(x,dict):
                    if x.get('path') and x.get('name') and not str(x['path']).endswith('/Preview.png'):
                        url=scoped_url(http,base,x['path']);ext=PurePosixPath(x['name']).suffix.lstrip('.').lower()
                        if ext in MEDIA or ext in {'zip','exr','hdr','mtl','bin'}:
                            originals.append({'url':url,'filename':x['name'],'relative_path':x['name'],'role':role,'variant':resolution or x.get('type',''),'bundle_key':resolution,'bytes':x.get('size')})
                    for k,val in x.items():
                        if isinstance(val,(dict,list)):walk(val,k if re.fullmatch(r'\d+[kK]',k) else resolution,'dependency' if k in {'textures','textureFiles'} else role)
                elif isinstance(x,list):
                    for val in x:walk(val,resolution,role)
            walk(info)
            originals=list({(v['url'],v['role']):v for v in originals}.values())
            if not originals:raise ValueError('Manifest contains no supported original files')
        preview=(v.get('preview') or {}).get('path','') or (v.get('basePath','')+'/'+v.get('preview',{}).get('name','') if v.get('preview',{}).get('name') else '')
        tags=v.get('tags',[])+[v.get('category',''),v.get('subCategory') or '','PBR' if media=='materials' else media]
        a=item(s['id'],media+'/'+name,name.replace('_',' '),types[media],'CC0-1.0','https://blendermaterials.com/PublicAPI','Lazytextures',tags,
               sorted({PurePosixPath(x['filename']).suffix.lstrip('.').lower() for x in originals}),files=originals,
               previews=[{'url':scoped_url(http,base,preview)}] if preview else [],
               revision=hashlib.sha256(json.dumps(info or v,sort_keys=True).encode()).hexdigest())
        a['features']={'provider_created_at':v.get('createdAt'),'manifest_scope':'Official current public Infos.json' if info else 'Selected original manifest is resolved on access'}
        if key or matches(a,{**f,'query':''}):rows.append(a)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Asset no longer appears in the public inventory')
        return rows[0]
    more=consumed<len(raw) or bool(d.get('pagination',{}).get('hasMore'))
    return {'items':rows,'next':str(offset+consumed) if more else None,'total':None,'scope':'Official public CC0 '+media+' inventory, originals resolved from the current public manifest'}


class Fields(HTMLParser):
    """Read licence/download fields only; never inherit sidebar/footer rights."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.fields={};self.heading=False;self.title=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='h1' or (tag=='h2' and 'title' in d.get('class','').split()):self.heading=True
        if tag in {'div','section'}:
            name=next((c.removeprefix('field-name-') for c in d.get('class','').split() if c.startswith('field-name-')),None)
            self.stack.append(name)
        name=next((n for n in reversed(self.stack) if n),None)
        if name:
            field=self.fields.setdefault(name,{'text':[],'links':[],'images':[]})
            if tag=='a' and d.get('href'):field['links'].append(d['href'])
            if tag=='img' and d.get('src'):field['images'].append(d['src'])
    def handle_endtag(self,tag):
        if tag in {'h1','h2'}:self.heading=False
        if tag in {'div','section'} and self.stack:self.stack.pop()
    def handle_data(self,data):
        if self.heading:self.title.append(data)
        name=next((n for n in reversed(self.stack) if n),None)
        if name:self.fields.setdefault(name,{'text':[],'links':[],'images':[]})['text'].append(data)


def oga_record(http,s,slug):
    from .live_providers import item
    if not re.fullmatch(r'[A-Za-z0-9_-]+',slug):raise ValueError('Invalid public art locator')
    url='https://opengameart.org/content/'+slug;body=http.text(url);p=Fields();p.feed(body)
    text=lambda name:' '.join(' '.join(p.fields.get(name,{}).get('text',[])).split())
    licence=None;evidence=''
    for u in p.fields.get('field-art-licenses',{}).get('links',[]):
        lic,ref=cc_license(u.replace('http://','https://',1))
        if lic in LICENSES and (licence is None or lic=='CC0-1.0'):licence,evidence=lic,ref
    if not licence:raise ValueError('Item has no supported per-item free licence')
    originals=[]
    for u in p.fields.get('field-art-files',{}).get('links',[]):
        u=scoped_url(http,'https://opengameart.org',u)
        name=PurePosixPath(urlsplit(u).path).name;ext=PurePosixPath(name).suffix.lstrip('.').lower()
        if ext in MEDIA or ext=='zip':originals.append({'url':u,'filename':name,'relative_path':name,'role':'main' if not originals else 'variant'})
    if not originals:raise ValueError('Item exposes no public original files')
    kind='audio' if 'Music' in text('field-art-type') or 'Sound' in text('field-art-type') else 'model-3d' if '3D' in text('field-art-type') else 'sprite'
    pack=any(v['filename'].lower().endswith('.zip') for v in originals) or len(originals)>1
    previews=[{'url':scoped_url(http,'https://opengameart.org',u)} for u in p.fields.get('field-art-preview',{}).get('images',[])[:3]]
    a=item(s['id'],slug,' '.join(p.title) or slug,'asset-pack' if pack else kind,licence,evidence,
           text('field-art-author') or text('field-art-authors'),[text('field-art-tags'),kind,'game'],
           [PurePosixPath(v['filename']).suffix.lstrip('.').lower() for v in originals],files=[] if pack else originals,
           previews=previews,description=text('body')[:2000],pack=slug if pack else '',revision=hashlib.sha256(json.dumps(originals,sort_keys=True).encode()).hexdigest())
    a['member_kind']=kind;a['_originals']=originals;a['attribution_notice']=text('field-art-attribution');a['origin_url']=url
    return a


def zip_members(http,s,parent,archive,filters,after,limit,key=None):
    from .live_providers import item,window
    from .content import ContentCache
    rows=[]
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-public-pack-') as directory:
        with ContentCache(directory,hosts=getattr(http,'hosts',())).remote_zip(archive['url']) as z:
            entries=z.infolist()
            if len(entries)>20000:raise ValueError('Archive listing exceeds request budget; narrow the selected pack')
            for v in entries:
                path=v.filename;ext=PurePosixPath(path).suffix.lstrip('.').lower();locator=parent['key']+'|'+archive['filename']+'|'+path
                if v.is_dir() or ext not in MEDIA or not acceptable(path) or review_terms(path) or (key and key!=locator):continue
                if path.startswith(('/','\\')) or '..' in PurePosixPath(path).parts:continue
                selected=[v]+[x for x in entries if not x.is_dir() and x!=v and (PurePosixPath(x.filename).name.lower().startswith(('license','licence','copying')) or (MEDIA[ext] in {'model-3d','scene-3d','animation-3d'} and PurePosixPath(x.filename).parent==PurePosixPath(path).parent and PurePosixPath(x.filename).suffix.lower() in {'.bin','.mtl','.png','.jpg','.jpeg'}))]
                files=[{'url':archive['url'],'archive_entry':x.filename,'filename':PurePosixPath(x.filename).name,'relative_path':x.filename,'bytes':x.file_size,'crc32':x.CRC,'role':'main' if x==v else 'license' if PurePosixPath(x.filename).name.lower().startswith(('license','licence','copying')) else 'dependency'} for x in selected]
                a=item(s['id'],locator,PurePosixPath(path).stem.replace('_',' '),MEDIA[ext],parent['license'],parent['license_url'],parent['author'],parent['tags']+[path],[ext],files=files,pack=parent['key'],revision=parent['revision']+':'+str(v.CRC)+':'+str(v.file_size))
                a['attribution_notice']=parent.get('attribution_notice','');rows.append(a)
    if key:
        if not rows:raise ValueError('Current pack no longer contains the selected original member')
        return rows[0]
    return window(rows,after,limit,filters)


def opengameart(http,s,f,after,limit,key=None):
    from .live_providers import item,matches,window
    pack=f.get('_pack_key') or (key.split('|',1)[0] if key else '')
    if pack:
        parent=oga_record(http,s,pack)
        if key and '|' not in key:return parent
        originals=parent.pop('_originals');rows=[];more=None
        for original in originals:
            if original['filename'].lower().endswith('.zip'):
                if key and key.split('|',2)[1]!=original['filename']:continue
                result=zip_members(http,s,parent,original,f,after,limit+1,key)
                if key:return result
                rows.extend(result['items']);more=more or result.get('next')
            else:
                locator=pack+'|'+original['filename'];ext=PurePosixPath(original['filename']).suffix.lstrip('.').lower()
                a=item(s['id'],locator,PurePosixPath(original['filename']).stem,MEDIA[ext],parent['license'],parent['license_url'],parent['author'],parent['tags'],[ext],files=[original],pack=pack,revision=parent['revision']);a['attribution_notice']=parent.get('attribution_notice','');rows.append(a)
        if key:
            a=next((a for a in rows if a['key']==key),None)
            if not a:raise ValueError('Public original member unavailable')
            return a
        result=window(rows,after,limit,f)
        if not result['next']:result['next']=more
        return result
    state=json.loads(after) if after else {'page':0,'skip':0}
    params={'keys':f.get('query') or s.get('query',''),'sort_by':'created','sort_order':'DESC','page':state['page']}
    if s.get('art_type'):params['field_art_type_tid[]']=s['art_type']
    body=http.text('https://opengameart.org/art-search-advanced?'+urlencode(params))
    # Only result title fields, never navigation/sidebar collections.
    titles=re.findall(r'class="field field-name-title\b.*?</div>',body,re.S)
    slugs=list(dict.fromkeys(slug for chunk in titles for slug in re.findall(r'href="/content/([A-Za-z0-9_-]+)"',chunk)))
    rows=[];consumed=state['skip'];errors=[]
    for slug in slugs[state['skip']:]:
        consumed+=1
        try:
            a=oga_record(http,s,slug)
            if matches(a,{**f,'query':''}):rows.append(a)
        except ValueError as e:errors.append({'item':slug,'reason':str(e)[:180]})
        if len(rows)==limit:break
    next_state={'page':state['page'],'skip':consumed} if consumed<len(slugs) else {'page':state['page']+1,'skip':0} if re.search(r'class="pager-next"',body) else None
    return {'items':rows,'next':json.dumps(next_state) if next_state else None,'total':None,'scope':'Current public art results with per-item licence and direct original/pack membership','item_errors':errors}


def internet_archive(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    state=json.loads(after) if after else {'position':0,'file_skip':0}
    position=state['position'];file_skip=state['file_skip'];pack=f.get('_pack_key')
    if key or pack:
        identifier,sep,member=(key or pack).partition('|');raw=[{'identifier':identifier}];position=0;total=1
    else:
        urls=[scheme+'://creativecommons.org/'+path for scheme in ('http','https') for path in ('publicdomain/zero/1.0/','licenses/by/4.0/','licenses/by/3.0/','licenses/by/2.0/','licenses/by-sa/4.0/','licenses/by-sa/3.0/')]
        query='('+ ' OR '.join('licenseurl:"'+url+'"' for url in urls)+')'
        query+=' AND mediatype:'+s.get('media','audio')
        for term in (s.get('query',''),f.get('query','')):
            if term:query+=' AND ('+re.sub(r'[^\w\s-]',' ',term)+')'
        params=[('q',query),('output','json'),('rows','20'),('page',str(position//20+1)),('fl[]','identifier'),('sort[]','downloads desc')]
        data=http.json('https://archive.org/advancedsearch.php?'+urlencode(params));raw=data.get('response',{}).get('docs',[]);total=data.get('response',{}).get('numFound',0)
    rows=[];consumed=position%20 if not (key or pack) else 0
    for result in raw[consumed:]:
        current_position=(position//20)*20+consumed;consumed+=1;identifier=result['identifier']
        if not re.fullmatch('[A-Za-z0-9_.-]{1,160}',identifier):continue
        d=http.json('https://archive.org/metadata/'+quote(identifier,safe=''));meta=d.get('metadata',{})
        if d.get('is_dark') or meta.get('access-restricted-item')=='true':continue
        licenses=meta.get('licenseurl',[]);licenses=licenses if isinstance(licenses,list) else [licenses]
        lic,evidence=next(((lic,evidence) for u in licenses for lic,evidence in [cc_license(str(u))] if lic in LICENSES),('unknown',''))
        if lic not in LICENSES:continue
        files=[]
        for v in d.get('files',[]):
            name=v.get('name','');ext=PurePosixPath(name).suffix.lstrip('.').lower()
            if ext not in MEDIA or v.get('source')!='original' or '..' in PurePosixPath(name).parts or not acceptable(name) or review_terms(name):continue
            if s.get('media')=='audio' and MEDIA[ext]!='audio':continue
            if s.get('media')=='movies' and MEDIA[ext] not in {'video','animation-2d'}:continue
            if s.get('media')=='image' and MEDIA[ext] not in {'image','illustration','texture','sprite'}:continue
            files.append(v)
        subject=meta.get('subject',[]);subject=subject if isinstance(subject,list) else [subject]
        creator=meta.get('creator','');creator='; '.join(creator) if isinstance(creator,list) else creator
        title=meta.get('title',identifier);title='; '.join(title) if isinstance(title,list) else title
        if key and sep:files=[v for v in files if v['name']==member]
        for index,v in enumerate(files):
            if index<file_skip:continue
            name=v['name'];ext=PurePosixPath(name).suffix.lstrip('.').lower();url='https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(name,safe='/');http.approve_content(url)
            a=item(s['id'],identifier+'|'+name,title+' — '+PurePosixPath(name).stem,MEDIA[ext],lic,evidence,str(creator),[str(t) for t in subject]+[s.get('query','')],[ext],
                   files=[{'url':url,'filename':PurePosixPath(name).name,'relative_path':name,'bytes':int(v.get('size',0)) or None,'md5':v.get('md5'),'role':'main'}],
                   description=plain(meta.get('description'))[:2000],pack=identifier,revision=v.get('md5') or str(d.get('item_last_updated','')))
            a['origin_url']='https://archive.org/details/'+identifier
            if key or matches(a,{**f,'query':''}):rows.append(a)
            if not key and len(rows)==limit:
                next_state={'position':current_position,'file_skip':index+1} if index+1<len(files) else {'position':current_position+1,'file_skip':0} if current_position+1<total else None
                return {'items':rows,'next':json.dumps(next_state) if next_state else None,'total':None,'scope':'Current per-file licensed public Archive originals; item tails are preserved in live cursors'}
        file_skip=0
    if key:
        if not rows:raise ValueError('Original no longer public or rights unverified')
        return rows[0]
    next_position=(position//20)*20+consumed
    return {'items':rows,'next':json.dumps({'position':next_position,'file_skip':0}) if next_position<total else None,'total':None,'scope':'Current individually licensed public Archive originals; no account/download-restricted items'}
