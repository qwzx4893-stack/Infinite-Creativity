"""Fresh audited LUT manifests, retaining upstream color-space caveats."""
import re
from pathlib import PurePosixPath
from urllib.parse import quote
from .color_adapters import COLLECTIONS
from .asset_adapters import complete_tree

def luts(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    repo='cyberhirsch/LUTr';meta=http.json('https://api.github.com/repos/'+repo);commit=http.json('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])['sha'];tree={e['path']:e for e in complete_tree(http,repo,commit,max_requests=16) if e['type']=='blob'};raw=f'https://raw.githubusercontent.com/{repo}/{commit}/';manifest=http.json(raw+'site/data/cube-manifest.json');verified={};notices={};rows=[]
    for r in sorted(manifest.get('luts',[]),key=lambda r:r['id']):
        if key and r['id']!=key or not key and r['id']<=after:continue
        group=r['collectionId'];license=r['license']
        if COLLECTIONS.get(group)!=license or f.get('_pack_key') and group!=f['_pack_key']:continue
        if group not in verified:
            if group=='freshluts-community':
                terms=re.sub('<[^>]+>',' ',http.text('https://freshluts.com/termsandconditions',1024*1024));verified[group]=bool(re.search('LUTs on Fresh LUTs are released under Creative Commons CC0',terms))
            else:
                match=re.fullmatch('https://github.com/([^/]+/[^/]+)',r['source'])
                if not match:verified[group]=False;continue
                try:notice=http.json('https://api.github.com/repos/'+match[1]+'/license')
                except ValueError:verified[group]=False;continue
                verified[group]=(notice.get('license') or {}).get('spdx_id')==license
                if verified[group] and notice.get('download_url'):notices[group]={'url':notice['download_url'],'filename':'LICENSE-'+group+'.txt','role':'license','sha':notice.get('sha')}
        if not verified[group]:continue
        normalized='site/'+r.get('clientLut','')
        if normalized not in tree and normalized+'.gz' in tree:normalized+='.gz'
        original=r.get('sourceFile','');original=original if original in tree else normalized
        if original not in tree:continue
        originals=[{'url':raw+quote(p,safe='/'),'filename':PurePosixPath(p).name.removesuffix('.gz'),'relative_path':p.removesuffix('.gz'),'sha':tree[p]['sha'],'bytes':tree[p].get('size'),'transport':'gzip' if p.endswith('.gz') else 'original','role':'main' if p==original else 'variant','content_variant':'Original source' if p==r.get('sourceFile') else 'Normalized/converted CUBE; inspect conversion warnings'} for p in dict.fromkeys([original,normalized]) if p in tree]
        if group in notices:originals.append(notices[group])
        a=item(s['id'],r['id'],r['title'],'lut',license,r['licenseUrl'],r.get('author') or r['source'],r.get('tags',[])+['editing','color-grading',r['collection']],['cube'],files=originals,pack=group,revision=tree[original]['sha'])
        a['features']={k:r.get(k) for k in ('transformClass','inputColorSpace','outputColorSpace','colorSpaceConfidence','inputGamut','inputTransfer','outputGamut','outputTransfer','cubeKind','size','conversionMethod','conversionWarning','sourceLabels')}
        if matches(a,f):rows.append(a)
        if not key and len(rows)>limit:break
    if key:
        if not rows:raise ValueError('LUT is no longer available with verified collection rights')
        return rows[0]
    return {'items':rows[:limit],'next':rows[limit-1]['key'] if len(rows)>limit else None,'total':None,'scope':'Current external LUT manifest and revalidated source licenses; no local catalog'}
