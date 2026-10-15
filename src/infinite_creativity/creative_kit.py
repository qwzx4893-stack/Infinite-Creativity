"""Request-only curation: diverse ranked selections and honest compatibility."""
import math,re
from concurrent.futures import ThreadPoolExecutor
from .policy import normalize_query,styles_for

ALLOWED={'query','kind','style','platform','format','source','section','pack'}
REQUIREMENTS={'format','rig_target','units','up_axis','rigged','animated','max_triangles','min_animations','min_width','min_height'}

def requirements(value):
    if not isinstance(value,dict) or set(value)-REQUIREMENTS:raise ValueError('Unknown compatibility requirement')
    for k,v in value.items():
        if k.startswith(('max_','min_')):
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('Numeric requirements must be finite nonnegative values')
        elif k in {'rigged','animated'}:
            if not isinstance(v,bool):raise ValueError('Rig/animation requirements must be boolean')
        elif not isinstance(v,str) or not v or len(v)>256:raise ValueError('Invalid compatibility requirement text')
    return value

def fit(a,requested):
    requested=requirements(requested);features=a.get('features',{});technical=features.get('declared_technical',{});usage=features.get('declared_usage',{})
    if not isinstance(technical,dict):technical={}
    if not isinstance(usage,dict):usage={}
    safety=a.get('admission',{}).get('safety',{});measured=safety.get('evidence',{}) if safety.get('state')=='original-media-screened' else {};checks=[]
    fields={'rig_target':usage.get('rigTarget'),'units':usage.get('units'),'up_axis':usage.get('upAxis'),'rigged':technical.get('rigged'),'animated':technical.get('animated'),'max_triangles':technical.get('triangleCount',technical.get('triangles')),'min_animations':technical.get('animationCount'),'min_width':technical.get('imageWidth'),'min_height':technical.get('imageHeight')}
    if 'animations' in technical and isinstance(technical['animations'],list):fields['min_animations']=len(technical['animations'])
    for name,wanted in requested.items():
        actual=fields.get(name);basis='current publisher declaration, not independently measured'
        if name=='format':actual=a.get('formats',[])
        if name=='max_triangles' and isinstance(measured.get('triangles'),int):actual=measured['triangles'];basis='reviewed selected original geometry'
        if name in {'min_width','min_height'} and safety.get('scope')=='original-raster' and safety.get('dimensions'):
            actual=safety['dimensions'][0 if name=='min_width' else 1];basis='reviewed original raster'
        if actual is None or actual==[]:state='unknown'
        elif name=='format':state='match' if wanted.lower() in actual else 'mismatch'
        elif name.startswith(('max_','min_')):
            if isinstance(actual,bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual):state='unknown'
            else:state='match' if (actual<=wanted if name.startswith('max_') else actual>=wanted) else 'mismatch'
        else:state='match' if (str(actual).lower()==str(wanted).lower()) else 'mismatch'
        checks.append({'requirement':name,'requested':wanted,'observed':actual,'state':state,'basis':basis})
    state='incompatible' if any(c['state']=='mismatch' for c in checks) else 'unverified' if not checks or any(c['state']=='unknown' for c in checks) else 'declared-compatible' if any(c['basis'].startswith('current publisher') for c in checks) else 'verified-selected-scope'
    return {'state':state,'checks':checks,'limits':'No automatic rig retargeting, unit conversion or artistic quality certification. Preview dimensions never satisfy original-size requirements.'}

def original_digest(a):
    safety=a.get('admission',{}).get('safety',{})
    return safety.get('sha256') if safety.get('state')=='original-media-screened' or safety.get('scope')=='original-raster' else None

def identity_keys(a):
    from .live import unseal
    loc=unseal(a['id'],'asset');keys={('item',loc['source'],loc['key'])}
    digest=original_digest(a);product=a.get('admission',{}).get('dedup_identity')
    if digest:keys.add(('original',digest))
    if product:keys.add(('product',product))
    safety=a.get('admission',{}).get('safety',{})
    if safety.get('scope')=='original-raster' and safety.get('decoded_pixel_sha256'):keys.add(('pixels',safety['decoded_pixel_sha256']))
    if safety.get('evidence',{}).get('structured_content_sha256'):keys.add(('structured-glb',safety['evidence']['structured_content_sha256']))
    return keys

def ranked(windows,brief,limit=4,max_per_source=2):
    from .live import unseal
    words=set(re.findall(r'[\w-]+',normalize_query(brief)));styles=set(styles_for(normalize_query(brief)));records={};duplicates=0
    for window_index,view in enumerate(windows):
        for position,a in enumerate(view.get('items',[])):
            if a.get('access') not in {'usable','usable-for-end-product'} or a.get('kind')=='asset-pack':continue
            loc=unseal(a['id'],'asset');digest=original_digest(a)
            product=a.get('admission',{}).get('dedup_identity');identity=('product',product) if product else ('original',digest) if digest else (loc['source'],loc['key'])
            text=(a['title']+' '+a.get('description','')+' '+' '.join(a.get('styles',[]))).lower()
            if identity not in records:records[identity]={'item':a,'rrf':0,'styles':sorted(styles&set(a.get('styles',[]))),'terms':sorted(w for w in words if len(w)>2 and w in text),'windows':set()}
            else:duplicates+=1
            record=records[identity]
            if window_index not in record['windows']:record['rrf']+=1/(60+position+1);record['windows'].add(window_index)
    ordered=sorted(records.values(),key=lambda r:(-len(r['styles']),-len(r['terms']),-r['rrf'],r['item']['title']))
    selected=[];counts={};seen=set()
    for row in ordered:
        a=row['item'];source=a['source']
        keys=identity_keys(a)
        if keys&seen:duplicates+=1;continue
        if counts.get(source,0)>=max_per_source:continue
        seen.update(keys)
        counts[source]=counts.get(source,0)+1
        selected.append({**a,'selection_evidence':{'reciprocal_rank_fusion':row['rrf'],'matched_styles':row['styles'],'matched_terms':row['terms'],'basis':'Admitted current results, metadata relevance and provider diversity. Not an aesthetic score.'}})
        if len(selected)>=limit:break
    return selected,duplicates

def build(library,brief,needs,limit_per_need=4,max_per_source=2):
    if not isinstance(brief,str) or len(brief)>2048 or not 1<=len(needs)<=6 or not 1<=limit_per_need<=8 or not 1<=max_per_source<=8:raise ValueError('Choose 1..6 needs, 1..8 results per need, and bounded brief/source diversity')
    for need in needs:
        if not isinstance(need,dict) or set(need)-ALLOWED-{'label','requirements'} or not isinstance(need.get('label'),str) or not need['label'] or len(need['label'])>128:raise ValueError('Each creative need requires a label and supported filters')
        if not all(isinstance(v,str) and len(v)<=2048 for k,v in need.items() if k!='requirements'):raise ValueError('Filters must be bounded text')
        if not need.get('section') and not need.get('kind'):raise ValueError('Each need must specify an exact section or kind')
        requirements(need.get('requirements',{}))
    if len({n['label'] for n in needs})!=len(needs):raise ValueError('Creative need labels must be unique')
    def query(need):
        # Independent per-slot live reads; no earlier result set or cache reused.
        local=type(library)(configs=library.sources);filters={k:v for k,v in need.items() if k in ALLOWED};views=[]
        try:
            view=local.open(limit=min(16,max(4,limit_per_need*2)),**filters);views.append(view)
            if not view.get('items') and view.get('next_cursor'):views.append(local.page(view['next_cursor'],min(16,max(4,limit_per_need*2))))
            items,duplicates=ranked(views,brief,limit_per_need,max_per_source)
            fitted=[]
            for a in items:
                original=local.raw_get(a['id']) if need.get('requirements') else None
                decision=fit(original,need['requirements']) if original else None
                if decision and decision['state']=='incompatible':continue
                fitted.append(a|({'fit':decision} if decision else {}))
            return {'label':need['label'],'filters':filters,'items':fitted,'review_queue':[a for v in views for a in v.get('review_queue',[])],'next_cursor':views[-1].get('next_cursor'),'sources':[s for v in views for s in v.get('sources',[])],'duplicates_removed':duplicates,'state':'candidates' if fitted else 'no-admitted-match-in-this-window'}
        except Exception as e:return {'label':need['label'],'items':[],'state':'unavailable','reason':str(e)[:300]}
        finally:
            if hasattr(local,'close'):local.close()
    with ThreadPoolExecutor(max_workers=3) as pool:groups=list(pool.map(query,needs))
    encountered=set()
    for group in groups:
        unique=[]
        for a in group['items']:
            keys=identity_keys(a)
            if keys&encountered:group['duplicates_removed']=group.get('duplicates_removed',0)+1;continue
            encountered.update(keys);unique.append(a)
        group['items']=unique
        if not unique and group['state']=='candidates':group['state']='no-distinct-admitted-match-in-this-window'
    return {'brief':brief,'groups':groups,'complete':all(g['items'] for g in groups),'storage':'No kit, original, metadata or vector index retained. Current signed locators/cursors are returned to the caller only.','next_actions':['assess_asset_fit','review_library_board','rank_library_items','asset_files'],'limits':'Current bounded windows, not exhaustive library coverage. Pending review is separate. The agent must judge artistic quality and coherence from actual previews.'}
