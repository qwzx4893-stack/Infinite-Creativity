"""Public presentation item windows; never infer reuse rights from zero price."""
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit

class PublicPage(HTMLParser):
    def __init__(self):super().__init__();self.entries=[];self.active=None;self.meta={};self.next='';self.jsonld=[];self.script=None
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='meta':self.meta[d.get('property') or d.get('name') or '']=d.get('content','')
        if tag=='a' and d.get('href'):
            self.active={'url':d['href'],'text':[],'images':[]}
            self.entries.append(self.active)
            if 'next' in d.get('rel','').split():self.next=d['href']
        if tag=='link' and 'next' in d.get('rel','').split() and d.get('href'):self.next=d['href']
        if tag=='img' and self.active:
            u=d.get('src') or d.get('data-src')
            if u:self.active['images'].append(u)
            if d.get('alt'):self.active['text'].append(d['alt'])
        if tag=='script' and d.get('type')=='application/ld+json':self.script=[]
    def handle_data(self,data):
        if self.active:self.active['text'].append(data)
        if self.script is not None:self.script.append(data)
    def handle_endtag(self,tag):
        if tag=='a':
            if self.active and ' '.join(self.active['text']).strip().lower() in {'next','next page','older','older posts','التالي'}:self.next=self.active['url']
            self.active=None
        if tag=='script' and self.script is not None:
            try:self.jsonld.append(json.loads(''.join(self.script)))
            except (ValueError,TypeError):pass
            self.script=None

def public_web(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    index=s.get('live_index',s['url']);host=urlsplit(index).hostname
    cursor=json.loads(after) if after else {'page':index,'after':''}
    url=urljoin(index,key) if key else cursor['page']
    if urlsplit(url).hostname!=host:raise ValueError('Public item locator leaves its configured provider')
    page=PublicPage();page.feed(http.text(url))
    if key:
        title=page.meta.get('og:title') or key.rsplit('/',1)[-1].replace('-',' ')
        preview=urljoin(url,page.meta.get('og:image','')) if page.meta.get('og:image') else ''
        a=item(s['id'],key,title,s.get('live_kind','visual-reference'),'unknown','',s.get('name',s['id']),tags=s.get('tags',[]),previews=[{'url':preview}] if preview else [],description=page.meta.get('og:description','')[:600],reference_preview=bool(preview));a['reference_category']='motion' if s['id']=='jitter' else 'illustration' if s['id']=='mockupbro' else 'interface';return a
    pattern=s.get('live_item_pattern')
    if not pattern:raise ValueError('No verified public item permalink pattern configured')
    entries={}
    for e in page.entries:
        absolute=urljoin(url,e['url']);path=urlsplit(absolute).path
        if urlsplit(absolute).hostname!=host or not re.search(pattern,path):continue
        name=' '.join(' '.join(e['text']).split())[:300] or path.rsplit('/',1)[-1].replace('-',' ')
        entries[path]=item(s['id'],path,name,s.get('live_kind','visual-reference'),'unknown','',s.get('name',s['id']),tags=s.get('tags',[]),previews=[{'url':urljoin(url,e['images'][0])}] if e['images'] else [],reference_preview=bool(e['images']))
        entries[path]['reference_category']='motion' if s['id']=='jitter' else 'illustration' if s['id']=='mockupbro' else 'interface'
    # JSON-LD ItemList is declarative data; no site JavaScript is executed.
    def structured(x):
        if isinstance(x,dict):
            if x.get('@type')=='ListItem' and isinstance(x.get('item'),dict):
                e=x['item'];u=e.get('url') or e.get('@id');path=urlsplit(urljoin(url,u)).path if isinstance(u,str) else ''
                if path and re.search(pattern,path):entries.setdefault(path,item(s['id'],path,e.get('name') or path.rsplit('/',1)[-1],s.get('live_kind','visual-reference'),description=str(e.get('description',''))[:600],tags=s.get('tags',[])))
            for v in x.values():structured(v)
        elif isinstance(x,list):
            for v in x:structured(v)
    for x in page.jsonld:structured(x)
    if not entries:raise ValueError('Public page exposes no supported item inventory; dynamic/authenticated content is not guessed or bypassed')
    rows=[a for k,a in sorted(entries.items()) if k>cursor['after'] and matches(a,f)];selected=rows[:limit]
    if len(rows)>limit:next_position=json.dumps({'page':url,'after':selected[-1]['key']},separators=(',',':'))
    else:
        next_url=urljoin(url,page.next) if page.next else ''
        if not next_url:
            current=int((re.search(r'[?&]page=(\d+)',url) or [None,'1'])[1])
            candidates=[]
            for e in page.entries:
                u=urljoin(url,e['url']);n=re.search(r'[?&]page=(\d+)',u)
                if n and int(n[1])>current and urlsplit(u).hostname==host and urlsplit(u).path==urlsplit(url).path:candidates.append((int(n[1]),u))
            if candidates:next_url=min(candidates)[1]
        next_position=json.dumps({'page':next_url,'after':''},separators=(',',':')) if next_url and urlsplit(next_url).hostname==host else None
    return {'items':selected,'next':next_position,'total':None,'scope':'Public item presentations only; original copying is withheld until individual reuse rights are verified'}
