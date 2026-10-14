"""Public creator presentation thumbnails, strictly separated from reusable originals."""
import hashlib,html,re,time
from pathlib import Path
from urllib.parse import urljoin
from .content import ContentCache

def quaternius_studies(c,fetch,run):
    cache=ContentCache(c.path.parent/'content');day=str(int(time.time()//86400));base='https://quaternius.com/'
    r=cache.fetch(base,'index.html',4*1024*1024,cache_revision=day);s=Path(r['path']).read_text(encoding='utf-8')
    matches=re.findall(r'<a\s+href=["\'](/packs/[A-Za-z0-9_-]+\.html)["\'][^>]*>\s*<img\b([^>]+)>',s,re.I)
    count=0;sid='inspiration:quaternius'
    c.source({'id':sid,'name':'Quaternius visual pack studies','url':base,'adapter':'public-creator-thumbnails','status':'reference-display-only','media':['visual-reference']})
    for path,attrs in matches:
        image=re.search(r'\bsrc=["\']([^"\']+)["\']',attrs)
        if not image:continue
        alt=re.search(r'\balt=["\']([^"\']*)["\']',attrs);slug=Path(path).stem
        title=html.unescape(alt[1]) if alt and alt[1].strip() else slug
        canonical=urljoin(base,path)+'#visual-study';preview=urljoin(base,image[1])
        if not preview.startswith(base+'assets/images/thumbnails/'):continue
        if not c.upsert(sid,slug,title,'visual-reference',canonical,author='Quaternius',tags=['cartoon','stylized','3D',slug],mode='reference',revision=hashlib.sha256((day+'|'+preview).encode()).hexdigest(),run=run):continue
        aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
        c.set_details(aid,{'reference_category':'three-d','description':'Study palette, silhouettes, modelling style and pack cohesion from the creator’s public presentation. Some packs offer paid Pro/source versions; only separately indexed free files are reusable.','files':[],'previews':[{'url':preview}],'reference_preview':{'scope':'public-presentation-thumbnail','publisher':'Quaternius','public_page':urljoin(base,path),'original_reuse':False,'paid_original_access':False,'notice':'Presentation thumbnail for visual study, credited to the creator. This does not grant rights to the thumbnail or paid original assets.'},'features':{'art_direction':['cartoon','stylized','low-poly'],'original_access':'Free/mixed-tier pack; originals require their own indexed license evidence'}});count+=1
    if not count:raise ValueError('Public thumbnail index unavailable')
    c.reconcile(sid,run);return count
