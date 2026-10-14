"""Optional explicit icon browsing; current source rights, no icon index."""
from urllib.parse import quote
from .policy import LICENSES

def icons(http,s,f,after,limit,key=None):
    from .live_providers import item,matches,window
    prefix=f.get('_pack_key') or (key.split(':',1)[0] if key else '')
    if not prefix and not f.get('query'):
        collections=http.json('https://api.iconify.design/collections');rows=[]
        for name,d in collections.items():
            rights=d.get('license') or {};a=item(s['id'],name,d.get('name',name),'asset-pack',rights.get('spdx','unknown'),rights.get('url',''),(d.get('author') or {}).get('name',''),['icons'],['svg'],pack=name);a['member_kind']='icon';rows.append(a)
        return window(rows,after,limit,f)
    if key and ':' not in key:
        d=http.json('https://api.iconify.design/collections?prefixes='+quote(key)).get(key)
        if not d:raise ValueError('Icon collection no longer available')
        rights=d.get('license') or {};a=item(s['id'],key,d.get('name',key),'asset-pack',rights.get('spdx','unknown'),rights.get('url',''),(d.get('author') or {}).get('name',''),['icons'],['svg'],pack=key);a['member_kind']='icon';return a
    if key:names=[key]
    elif prefix:
        data=http.json('https://api.iconify.design/collection?prefix='+quote(prefix));local=list(data.get('uncategorized',[]))
        for v in data.get('categories',{}).values():local.extend(v)
        local+=list(data.get('icons',[]));names=[prefix+':'+n for n in sorted(set(local))]
    else:
        data=http.json('https://api.iconify.design/search?query='+quote(f['query'])+'&limit='+str(max(32,limit))+'&start='+str(int(after or 0)));names=data.get('icons',[])
    groups=sorted({n.split(':',1)[0] for n in names});collections=http.json('https://api.iconify.design/collections?prefixes='+quote(','.join(groups))) if groups else {};rows=[]
    for n in names:
        p,name=n.split(':',1);d=collections.get(p,{}) or {};rights=d.get('license') or {};url='https://api.iconify.design/'+quote(p)+'/'+quote(name)+'.svg'
        rows.append(item(s['id'],n,name.replace('-',' '),'icon',rights.get('spdx','unknown'),rights.get('url',''),(d.get('author') or {}).get('name',''),[d.get('name',p),'icon'],['svg'],files=[{'url':url,'filename':name+'.svg','role':'main'}],pack=p,revision=str(d.get('version',''))))
    if key:
        if not rows:raise ValueError('Icon unavailable in current collection')
        return rows[0]
    if prefix:return window(rows,after,limit,f)
    selected=[];consumed=0
    for a in rows:
        consumed+=1
        if matches(a,f):selected.append(a)
        if len(selected)==limit:break
    total=data.get('total')
    more=consumed<len(rows) or isinstance(total,int) and int(after or 0)+consumed<total or len(names)>=max(32,limit)
    return {'items':selected,'next':str(int(after or 0)+consumed) if more and consumed else None,'total':None,'scope':'Current official icon search; collection rights checked in this request'}
