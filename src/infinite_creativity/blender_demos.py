"""Per-card official Blender demos, including animation, sculpting and editing projects."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import hashlib,json,re,time
from .content import ContentCache
from .curation import record

class Cards(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.current=None;self.cards=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            if self.current:self.depth+=1
            elif 'cards-item' in attrs.get('class','').split():self.current={'text':[],'links':[],'images':[]};self.depth=1
        if self.current:
            if tag=='a' and attrs.get('href'):self.current['links'].append(attrs['href'].strip())
            if tag=='img' and attrs.get('src'):self.current['images'].append(attrs['src'])
    def handle_endtag(self,tag):
        if tag=='div' and self.current:
            self.depth-=1
            if self.depth==0:self.cards.append(self.current);self.current=None
    def handle_data(self,data):
        if self.current:self.current['text'].append(data)

def demos(c,fetch,run):
    page='https://www.blender.org/download/demo-files/';cache=ContentCache(c.path.parent/'content')
    r=cache.fetch(page,'demos.html',8*1024*1024,cache_revision=str(int(time.time()//86400)))
    parser=Cards();parser.feed(Path(r['path']).read_text(encoding='utf-8',errors='replace'));count=0
    c.source({'id':'blender-demos','name':'Blender official demo files','url':page,'adapter':'blender-demos','status':'per-card-license','media':['scene-3d','animation-3d','animation-2d','editing-template','shader']})
    for card in parser.cards:
        text=' '.join(' '.join(card['text']).split())
        links=list(dict.fromkeys(urljoin(page,u) for u in card['links'] if urlsplit(urljoin(page,u)).hostname in {'download.blender.org','www.blender.org'} and urlsplit(u).path.lower().endswith(('.blend','.zip','.mp4','.7z'))))
        if not links:continue
        evidence=next((u.replace('http://','https://',1) for u in card['links'] if 'creativecommons.org/licenses/' in u or 'creativecommons.org/publicdomain/' in u),'')
        lic='CC0-1.0' if re.search(r'\bCC-?0\b',text) else 'CC-BY-4.0' if '/by/4.0' in evidence else 'CC-BY-3.0' if '/by/3.0' in evidence else 'unknown'
        if lic=='CC0-1.0':evidence=page
        kind='animation-2d' if re.search('grease|pencil|2d',text,re.I) else 'animation-3d' if re.search('animation|rig|pose',text,re.I) else 'editing-template' if re.search('sequencer|editing',text,re.I) else 'shader' if re.search('shader|shading',text,re.I) else 'scene-3d'
        canonical=links[0];title=text.split('Requires Blender')[0][:180] or Path(urlsplit(canonical).path).name
        files=[{'url':u,'filename':Path(urlsplit(u).path).name,'role':'main' if i==0 else 'variant'} for i,u in enumerate(links)]
        if not c.upsert('blender-demos',canonical,title,kind,canonical,license=lic,license_url=evidence,author=text[:300],tags=['Blender','professional-demo',text],platforms=['film','game','desktop'],formats=sorted({Path(f['filename']).suffix.lstrip('.') for f in files}),access_url=canonical,revision=hashlib.sha256(text.encode()).hexdigest(),mode='usable' if lic!='unknown' else 'reference',run=run):continue
        aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
        images=[urljoin(page,u) for u in card['images']]
        c.set_details(aid,{'pack_name':title,'pack_scope':canonical,'description':text,'files':files if lic!='unknown' else [],'previews':[{'url':u} for u in images[:1]] if lic!='unknown' else [],'features':{'original_projects':True,'license_scope':'Only the license stated on this official demo card; no subscription vault files.','blender_requirements':text.split('Requires Blender')[-1] if 'Requires Blender' in text else 'Inspect original file metadata'}})
        if re.search('human base mesh',text,re.I):record(c,aid,safety='review-required',evidence={'metadata_review':{'reason':'Anatomical human base meshes may be unclothed; withheld pending original-content review'}})
        count+=1
    if not count:raise ValueError('Official demo cards unavailable')
    c.reconcile('blender-demos',run);return count
