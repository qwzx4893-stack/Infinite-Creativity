"""Official free-asset API. Original delivery follows current per-item permissions."""
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote,urlsplit

def blendkit(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    base='https://www.blendkit.com/api/v1/'
    if key:
        if not re.fullmatch('[a-fA-F0-9-]{36}',key):raise ValueError('Invalid official asset identifier')
        data=http.json(base+'assets/'+key+'/');raw=[data]
    else:
        query=(f.get('query','')+' +is_free:true').strip()
        if f.get('kind'):query+=' +asset_type:'+{'model-3d':'model','scene-3d':'scene','material':'material','brush':'brush','texture':'texture','hdri':'hdr'}.get(f['kind'],f['kind'])
        page=int(after or 1);data=http.json(base+'search/?query='+quote(query,safe='')+'&page_size='+str(limit)+'&page='+str(page));raw=data.get('results',[])
    rows=[]
    for a in raw:
        if a.get('isPrivate'):continue
        free=a.get('isFree') is True and a.get('access') in {'free',None}
        license='CC0-1.0' if a.get('license') in {'cc_zero','cc0'} and free else 'LicenseRef-Blendkit-RoyaltyFree' if a.get('license')=='royalty_free' and free else 'unknown'
        author=a.get('author') or {};author=' '.join(str(author.get(k,'')) for k in ('firstName','lastName')).strip() or str(author.get('id','')) if isinstance(author,dict) else str(author)
        previews=[];files=[]
        for v in a.get('files',[]):
            if v.get('isThumbnail') or v.get('fileType')=='thumbnail':
                thumb=v.get('thumbnailMiddleUrl') or v.get('fileThumbnailLarge') or v.get('fileThumbnail')
                if thumb:previews.append({'url':thumb})
            elif free and license!='unknown' and v.get('downloadUrl'):
                u=v['downloadUrl']
                # Only selected-item reads resolve official download descriptors.
                files.append({'url':u,'filename':PurePosixPath(v.get('filename','asset.blend')).name,'relative_path':v.get('filename','asset.blend'),'bytes':v.get('fileUploadSize'),'variant':v.get('fileType'),'role':'variant'})
        tags=a.get('tags') or []
        tags=[x.get('name','') if isinstance(x,dict) else str(x) for x in tags]
        record=item(s['id'],a['id'],a.get('displayName') or a.get('name') or a['id'],{'model':'model-3d','scene':'scene-3d','material':'material','brush':'brush','hdr':'hdri'}.get(a.get('assetType'),'model-3d'),license,'https://www.blendkit.com/docs/licenses/',author,tags,sorted({PurePosixPath(v['filename']).suffix.lstrip('.') for v in files}),files=files,previews=previews[:1],description=re.sub('<[^>]+>',' ',a.get('description') or '')[:800],revision=str(a.get('versionNumber',''))+':'+str(a.get('lastBlendUpload') or a.get('created','')),reference_preview=bool(previews))
        record['end_product_only_verified']=license=='LicenseRef-Blendkit-RoyaltyFree'
        record['reuse_scope']='End products only; raw asset redistribution, resale and asset-pack/library mirroring are not permitted.' if record['end_product_only_verified'] else 'Original item license applies.'
        if matches(record,f):rows.append(record)
    if key:
        if not rows:raise ValueError('Item is no longer public or eligible')
        return rows[0]
    return {'items':rows,'next':str(page+1) if data.get('next') else None,'total':None,'scope':'Fresh official free-asset search; original access and per-item rights revalidated when selected'}
