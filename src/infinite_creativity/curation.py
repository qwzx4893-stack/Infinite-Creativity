"""Evidence-based curation. Intentional minimal, pixel and low-poly styles are retained."""
import hashlib
import json
import re
from .catalog import now
from .policy import acceptable, review_terms,styles_for

def record(c,asset_id,*,quality=None,safety=None,duplicate=None,evidence=None):
    a=c.db.execute('SELECT revision FROM assets WHERE id=?',(asset_id,)).fetchone()
    if not a:raise ValueError('Unknown item')
    old=c.db.execute('SELECT * FROM curation WHERE asset_id=?',(asset_id,)).fetchone()
    data=json.loads(old['data']) if old and old['revision']==a['revision'] else {}
    if evidence:data.update(evidence)
    def state(field,new,default):return new if new is not None else old[field] if old and old['revision']==a['revision'] else default
    c.db.execute('INSERT OR REPLACE INTO curation VALUES (?,?,?,?,?,?)',(asset_id,a['revision'],state('quality_state',quality,'not-assessed'),state('safety_state',safety,'metadata-only'),state('duplicate_of',duplicate,''),json.dumps(data,ensure_ascii=False)))

def signature(a,d):
    meaningful=[f for f in d.get('files',[]) if f.get('role') not in {'license','preview','provenance'}]
    if not meaningful:return None
    entries=[]
    for f in meaningful:
        digest=f.get('sha256') or f.get('sha')
        if not isinstance(digest,str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',digest):return None
        entries.append((f.get('role','main'),f.get('relative_path',f.get('filename','')).rsplit('/',1)[-1] if f.get('role')=='dependency' else '',digest))
    notices=sorted(f.get('sha256') or f.get('sha') or f.get('url','') for f in d.get('files',[]) if f.get('role')=='license')
    rights=(a['license'],a['author'] if a['license']!='CC0-1.0' else '',(notices or [a['license_url']]) if a['license']!='CC0-1.0' else [])
    return hashlib.sha256(json.dumps([rights,sorted(set(entries))],sort_keys=True).encode()).hexdigest()

def curate(c):
    known={};duplicates=0;flagged=0;assessed=0
    c.db.execute("UPDATE curation SET duplicate_of='' WHERE duplicate_of!=''")
    rows=c.db.execute('SELECT a.rowid internal_rowid,a.*,d.data details_json FROM assets a LEFT JOIN asset_details d ON d.asset_id=a.id WHERE a.active=1 ORDER BY a.first_seen,a.id')
    for row in rows:
        a=dict(row);d=json.loads(a.pop('details_json') or '{}');text=a['title']+' '+a['tags']
        styles=styles_for(a['title']+' '+' '.join(json.loads(a['tags'])))
        if json.loads(a['styles'])!=styles:
            c.db.execute('UPDATE assets SET styles=? WHERE id=?',(json.dumps(styles),a['id']))
            c.db.execute('UPDATE assets_fts SET styles=? WHERE rowid=?',(' '.join(styles),a['internal_rowid']))
        if not acceptable(text) or review_terms(text):
            record(c,a['id'],safety='review-required',evidence={'metadata_review':{'reason':'Explicit or potentially suggestive language; excluded pending contextual review','at':now()}});flagged+=1
        main=[f for f in d.get('files',[]) if f.get('role','main') in {'main','variant'}]
        if main and all(f.get('bytes')==0 for f in main):
            record(c,a['id'],quality='rejected',evidence={'technical_quality':{'reason':'All indexed original variants have zero bytes','at':now()}})
        sig=signature(a,d)
        if sig:
            assessed+=1
            if sig in known:
                record(c,a['id'],duplicate=known[sig],evidence={'duplicate':{'method':'Exact upstream cryptographic hashes for the full original/dependency bundle, compatible rights','signature':sig,'at':now()}});duplicates+=1
            else:known[sig]=a['id']
    c.db.commit()
    return {'full_bundles_with_crypto_evidence':assessed,'exact_duplicates_hidden':duplicates,'metadata_quarantines':flagged,'aesthetic_quality':'Not automatically rated. Minimalism, pixel art, low-poly and small dimensions are not rejection rules.'}

def report(c):
    rows=c.db.execute('SELECT r.* FROM curation r JOIN assets a ON a.id=r.asset_id WHERE a.active=1')
    states={};quality={};duplicates=0;vision=0;original=0;context=0
    for r in rows:
        states[r['safety_state']]=states.get(r['safety_state'],0)+1;quality[r['quality_state']]=quality.get(r['quality_state'],0)+1;duplicates+=bool(r['duplicate_of'])
        data=json.loads(r['data']);scope=data.get('vision',{}).get('scope','')
        vision+=bool(scope);original+=scope=='original-raster'
        context+=bool(data.get('context_review'))
    total=c.db.execute('SELECT count(*) FROM assets WHERE active=1').fetchone()[0]
    return {'safety_states':states,'quality_states':quality,'exact_duplicate_aliases':duplicates,'visual_reviews':vision,'context_reviews':context,'original_rasters_screened':original,'without_visual_review':total-vision,'limits':'Automated image screening is probabilistic, uncalibrated for many game sprites, and scoped to recorded images. Context reviews can supersede false positives with recorded hash-bound evidence. Unseen geometry/frames/speech and aesthetic quality remain unassessed.'}

def apply_reviews(c,items):
    if not isinstance(items,list) or len(items)>10000:raise ValueError('Expected at most 10000 review records')
    n=0
    for item in items:
        a=c.get(item['asset_id']);row=c.db.execute('SELECT data FROM curation WHERE asset_id=?',(item['asset_id'],)).fetchone()
        data=json.loads(row[0]) if row else {};vision=data.get('vision',{})
        if not a or a['revision']!=item['revision'] or vision.get('sha256')!=item['media_sha256']:raise ValueError('Review media/revision differs from the recorded item')
        if item.get('decision') not in {'safe','reject-sexual','needs-review'} or not item.get('reviewer') or not item.get('reason'):raise ValueError('Review decision, reviewer and actual context reason required')
        state={'safe':'context-reviewed','reject-sexual':'blocked','needs-review':'review-required'}[item['decision']]
        record(c,a['id'],safety=state,evidence={'context_review':{**item,'scope':vision['scope'],'at':now(),'method':'Explicit operator context review; no inference of unseen media'}});n+=1
    c.db.commit();return {'context_reviews_applied':n}
