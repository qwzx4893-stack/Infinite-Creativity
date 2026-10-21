"""Progressive, type-specific selection without a retained asset inventory.

Cheap evidence is used first. Original-source analysis is bounded to the
current page; uncertainty is queued rather than renamed professional quality.
"""
import hashlib
import json
from .request_scope import checkpoint


def policy():
    return {
        'default': 'useful', 'scope': 'Every MCP browsing page and its continuation',
        'stages': ['current rights and content policy', 'exact duplicate identities',
                   'bounded original technical evidence', 'type-specific utility',
                   'photographic aesthetic threshold when applicable'],
        'excluded': ['empty originals', 'invalid syntax/media', 'empty component bodies',
                     'below-threshold photographic estimates', 'exact byte/pixel/bundle duplicates',
                     'identical parsed source bundles with identical rights notices'],
        'preserved': ['intentional minimalism', 'pixel art', 'low-poly', 'distinct materials/poses',
                      'source notices and dependencies'],
        'uncertain': 'quality_queue; metadata is not an approved high-quality original',
        'storage': 'No retained items, scores, originals or embeddings. Cursor receipts are bounded hashes.',
        'limits': 'No universal artistic certification or global permanent deduplication. Coverage grows with actual page traversal; this is not a completed scan of every upstream original.'}


def report():
    return {'evaluated': 0, 'selected': 0, 'excluded': 0, 'queued': 0,
            'duplicates': 0, 'navigation': 0, 'reasons': {},
            'scope': 'Current bounded live page; continue its cursor for further coverage.'}


def choose(library, asset, card, filters, summary, admission):
    checkpoint()
    if asset.get('navigation_only') or asset['kind']=='asset-pack':
        summary['navigation']+=1
        card['curation']={'state':'navigation-only','quality_claim':False}
        return 'selected'
    summary['evaluated']+=1
    originals=[f for f in asset.get('files',[]) if f.get('role','main') in {'main','variant'}]
    decision='queue';reason='original-quality-evidence-unavailable'
    assessment=None
    if originals and all(f.get('bytes')==0 for f in originals):
        decision,reason='excluded','empty-original'
    else:
        from .live_quality import assess_record
        try:
            assessment=assess_record(library,asset,card['id'],filters.get('_min_aesthetic',5.5))
            technical=assessment.get('technical',{})
            selection=assessment['selection']
            if selection in {'rejected','below-photo-aesthetic-threshold'}:
                decision,reason='excluded',selection
            elif technical.get('substance',{}).get('state')=='empty-component' and asset['kind'] in {'ui-component','template'}:
                decision,reason='excluded','empty-component'
            elif selection=='aesthetic-candidate':
                decision,reason='selected','estimated-photo-aesthetics-and-original-validity'
            elif asset.get('software_only') and technical.get('state')=='syntax-checked':
                # This is useful original code, not a rendered-art score. Missing
                # package imports remain actionable integration requirements.
                decision,reason='selected','complete-parsed-original-source'
                normalized=technical.get('normalized_source_sha256')
                notices=sorted((f.get('sha256') or f.get('sha') or f.get('url','')) for f in asset.get('files',[]) if f.get('role') in {'license','provenance'})
                if normalized and notices:
                    digest=hashlib.sha256(json.dumps([normalized,asset['license'],notices],sort_keys=True).encode()).hexdigest()
                    identity='parsed-source-bundle:'+digest
                    if identity in admission.seen:
                        decision,reason='excluded','identical-parsed-source-and-rights'
                        summary['duplicates']+=1
                    else:
                        admission.seen.add(identity);admission.seen_order.append(identity)
            elif not asset.get('software_only'):
                safety=asset.get('admission',{}).get('safety',{})
                if safety.get('state') in {'original-media-screened','selected-original-screened','reviewer-approved'} or safety.get('scope')=='original-raster':
                    # A photographic original with an unavailable model cannot
                    # be silently promoted to the photo threshold's passing set.
                    if safety.get('scope')=='original-raster' and 'photography' in asset.get('tags',[]):
                        reason='photographic-aesthetic-estimate-unavailable'
                    else:decision,reason='selected','reviewed-original-technical-evidence'
        except (ValueError,OSError,ImportError,RuntimeError) as error:
            reason='quality-evidence-unavailable'
            assessment={'reason':str(error)[:240]}
    card['curation']={'state':decision,'reason':reason,'professional_guarantee':False,
                      'basis':'Type-specific current original evidence; source syntax does not certify visual design.'}
    if assessment:card['quality_assessment']=assessment
    summary['reasons'][reason]=summary['reasons'].get(reason,0)+1
    summary[{'selected':'selected','excluded':'excluded','queue':'queued'}[decision]]+=1
    return decision
