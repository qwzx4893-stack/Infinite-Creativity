"""Licensed color-grading and technical LUT packs with explicit color-management assumptions."""
import hashlib,json,re,time
from pathlib import Path,PurePosixPath
from urllib.parse import quote
from .content import ContentCache,CONTENT_HOSTS
from .asset_adapters import complete_tree
from .policy import LICENSES

COLLECTIONS={'freshluts-community':'CC0-1.0','stripedpurple-color-grading-luts':'MIT','jonmatifa-a6000-luts':'CC0-1.0','sguyader-filmsim':'CC0-1.0','videovillage-red-conversion-luts':'MIT','andrewwillmott-colour-blind-luts':'Unlicense','aswf-opencolorio-config-aces':'BSD-3-Clause'}

def luts(c,fetch,run):
    repo='cyberhirsch/LUTr';meta=fetch.json('https://api.github.com/repos/'+repo);commit=fetch.json('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])['sha']
    tree={e['path']:e for e in complete_tree(fetch,repo,commit) if e['type']=='blob'}
    raw='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'
    manifest=fetch.json(raw+'site/data/cube-manifest.json')
    cache=ContentCache(c.path.parent/'content');CONTENT_HOSTS.add('freshluts.com')
    received=cache.fetch('https://freshluts.com/termsandconditions','terms.html',1024*1024,cache_revision=str(int(time.time()//86400)))
    terms=Path(received['path']).read_text(encoding='utf-8',errors='replace')
    if not re.search('LUTs on Fresh LUTs are released under Creative Commons CC0',re.sub('<[^>]+>',' ',terms)):raise ValueError('Fresh LUTs license terms changed; retain previous snapshot')
    verified={'freshluts-community':True};notices={};count=0;sources=set()
    for r in manifest['luts']:
        group=r['collectionId'];lic=r['license']
        if COLLECTIONS.get(group)!=lic or lic not in LICENSES:continue
        if group not in verified:
            match=re.fullmatch(r'https://github.com/([^/]+/[^/]+)',r['source'])
            if not match:verified[group]=False;continue
            try:upstream=fetch.json('https://api.github.com/repos/'+match[1]+'/license')
            except RuntimeError as e:
                if 'HTTP 404 ' not in str(e):raise
                verified[group]=False;continue
            verified[group]=(upstream.get('license') or {}).get('spdx_id')==lic
            if verified[group] and upstream.get('download_url'):notices[group]={'url':upstream['download_url'],'filename':'LICENSE-'+group+'.txt','role':'license','sha':upstream.get('sha')}
        if not verified[group]:continue
        original=r.get('sourceFile','');normalized='site/'+r.get('clientLut','')
        if normalized not in tree and normalized+'.gz' in tree:normalized+='.gz'
        original=original if original in tree else normalized
        if original not in tree:continue
        sid='lut-pack:'+group;canonical='https://github.com/'+repo+'#lut-'+r['id']
        c.source({'id':sid,'name':r['collection'],'url':r['source'],'adapter':'lut-manifest','status':'per-collection-verified-license','media':['lut']});sources.add(sid)
        if not c.upsert(sid,r['id'],r['title'],'lut',canonical,license=lic,license_url=r['licenseUrl'],author=r.get('author') or r['source'].rsplit('/',1)[-1],tags=r.get('tags',[])+['editing','color-grading',r['collection']],platforms=['film','desktop','game'],formats=['cube' if original.endswith('.cube.gz') else PurePosixPath(original).suffix.lstrip('.').lower()],access_url=raw+quote(original,safe='/'),revision=tree[original]['sha'],run=run):continue
        aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
        files=[]
        for path in dict.fromkeys([original,normalized]):
            if path in tree:files.append({'url':raw+quote(path,safe='/'),'filename':PurePosixPath(path).name.removesuffix('.gz'),'relative_path':path.removesuffix('.gz'),'sha':tree[path]['sha'],'bytes':tree[path].get('size'),'transport':'gzip' if path.endswith('.gz') else 'original','role':'main' if not files else 'variant','content_variant':'Original source' if path==r.get('sourceFile') else 'Metadata-normalized CUBE; read conversionMethod and conversionWarning'})
        if group in notices:files.append(notices[group])
        preview='site/'+r.get('previewAtlas','')
        c.set_details(aid,{'pack_name':r['collection'],'pack_scope':group,'description':'Licensed LUT with declared or explicitly inferred input/output encoding. Test on representative footage before use.','files':files,'previews':[{'url':raw+quote(preview,safe='/')}] if preview in tree else [],'legal':[{'license':lic,'evidence':r['licenseUrl'],'attribution':r.get('attribution')}],'features':{k:r.get(k) for k in ('transformClass','inputColorSpace','outputColorSpace','colorSpaceConfidence','inputGamut','inputTransfer','outputGamut','outputTransfer','cubeKind','size','conversionMethod','conversionWarning','sourceLabels')},'provenance':{'source_original':r.get('assetUrl') or r['source'],'upstream_original_sha256':r.get('sourceSha256'),'conversion_source':'LUTr metadata manifest; original and converted variants are labelled separately'}});count+=1
    for sid in sources:c.reconcile(sid,run)
    if not count:raise ValueError('No licensed transform originals or converted variants found; refusing an empty inventory')
    return count
