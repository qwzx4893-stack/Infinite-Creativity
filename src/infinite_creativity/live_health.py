"""Current source evidence, never an inventory or retained health database."""
import time
from concurrent.futures import ThreadPoolExecutor

def probe(library,source_ids,query='',limit=1):
    if not isinstance(source_ids,list) or not 1<=len(source_ids)<=8 or len(set(source_ids))!=len(source_ids) or any(s not in library.sources for s in source_ids) or not isinstance(query,str) or len(query)>2048 or not 1<=limit<=3:raise ValueError('Choose 1..8 distinct configured sources and 1..3 samples')
    def inspect(source):
        started=time.monotonic()
        with type(library)(configs=library.sources) as local:
            try:
                view=local.open(source=source,query=query,limit=limit);items=view.get('items',[]);pending=view.get('review_queue',[]);originals=[a for a in items if a.get('access') in {'usable','usable-for-end-product'} and (a.get('admission',{}).get('safety',{}).get('state') in {'original-media-screened','selected-original-screened'} or a.get('admission',{}).get('safety',{}).get('scope')=='original-raster') and a.get('kind')!='asset-pack'];navigation=[a for a in items if a.get('access')=='pack-navigation-only'];failures=[s for s in view.get('sources',[]) if s.get('status')=='unavailable']
                state='unavailable' if failures else 'original-sample-admitted' if originals else 'metadata-working-original-pending' if pending else 'navigation-only-sample' if navigation else 'preview-or-metadata-sample' if items else 'no-admitted-match-in-this-window'
                return {'source':source,'state':state,'admitted_original_samples':len(originals),'pending_samples':len(pending),'navigation_samples':len(navigation),'other_samples':len(items)-len(originals)-len(navigation),'has_continuation':bool(view.get('next_cursor')),'failures':failures,'admission':view.get('admission',{}),'seconds':round(time.monotonic()-started,3),'performance':local.http.metrics()}
            except Exception as e:return {'source':source,'state':'unavailable','reason':str(e)[:300],'seconds':round(time.monotonic()-started,3)}
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(inspect,source_ids))
    return {'sources':rows,'scope':'Current bounded samples only. Registration, public metadata, pack navigation, screened previews and admitted originals are separate states. No sample proves full-site coverage.','storage':'No health, item, original or latency history retained; rerun for current evidence.'}
