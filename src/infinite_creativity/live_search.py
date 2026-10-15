"""Bounded batched exploration and explainable metadata relevance ranking."""
import re
from concurrent.futures import ThreadPoolExecutor
from .policy import normalize_query,styles_for


def batch(l,searches,limit=10):
    if not 1<=len(searches)<=8 or not 1<=limit<=30:raise ValueError('Choose 1..8 searches, each 1..30 results')
    allowed={'query','kind','style','platform','format','mode','source','section','pack','license'}
    for filters in searches:
        if not isinstance(filters,dict) or set(filters)-allowed or not all(isinstance(v,str) for v in filters.values()):raise ValueError('Invalid search filters')
    def query(filters):
        owned=hasattr(l,'sources');local=type(l)(configs=l.sources) if owned else l
        try:
            view=local.open(limit=limit,**filters)
            if hasattr(local,'http') and hasattr(local.http,'metrics'):view['performance']=local.http.metrics()
            return {'filters':filters,'view':view}
        except ValueError as e:return {'filters':filters,'error':str(e)[:400]}
        finally:
            if owned:local.close()
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(query,searches))
    return {'searches':rows,'storage':'No saved results; independent bounded live scopes execute with concurrency <=3','continuation':'Continue each successful view with its own next_cursor'}


def recommend(l,direction,kinds,platform,limit):
    if not 1<=limit<=30 or len(direction)>2048 or len(kinds)>8:raise ValueError('Invalid art-direction brief')
    normalized=normalize_query(direction);styles=styles_for(normalized)
    # Use multiple medium windows. A prose brief is not a literal AND search.
    words=[w for w in re.findall(r'[\w-]+',normalized) if w not in {'a','an','the','with','for','and','of','in','to','want','need','اريد','أريد','مع','من','في','على','و'}]
    query=' '.join(words[:3])
    searches=[dict(kind=k,platform=platform,query=query,**({'style':styles[0]} if styles else {})) for k in (kinds or [''])]
    result=batch(l,searches,min(30,max(3,limit)));candidates=[];seen=set()
    for response in result['searches']:
        for a in response.get('view',{}).get('items',[]):
            from .live import unseal
            locator=unseal(a['id'],'asset');identity=(locator['source'],locator['key'])
            if identity in seen:continue
            seen.add(identity)
            text=(a['title']+' '+a['description']).lower();matched_styles=sorted(set(styles)&set(a['styles']))
            score=4*len(matched_styles)+sum(1 for word in words if word in text)+(2 if platform and platform in a['platforms'] else 0)
            candidates.append({**a,'recommendation':{'score':score,'matched_styles':matched_styles,'basis':'Current metadata, rights and admission evidence; not a visual-embedding or aesthetic-quality guarantee'}})
    candidates.sort(key=lambda a:(-a['recommendation']['score'],a['title']))
    return {'items':candidates[:limit],'searches':result['searches'],'art_direction':direction,'styles_detected':styles,'records':None,'next_action':'Use each search view cursor to widen this live candidate pool'}
