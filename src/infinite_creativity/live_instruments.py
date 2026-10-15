"""Publisher instrument manifests joined to real public original files per RPC."""
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote
from .asset_adapters import complete_tree


def instruments(http, source, filters, after, limit, key=None):
    from .live_providers import item, window
    repo = 'facebookincubator/Meta-open-sound'
    commit = http.json('https://api.github.com/repos/' + repo + '/commits/main')['sha']
    if not re.fullmatch('[0-9a-f]{40}', commit): raise ValueError('Invalid public instrument revision')
    tree = {x['path']: x for x in complete_tree(http, repo, commit, max_requests=8) if x.get('type') == 'blob'}
    raw = 'https://raw.githubusercontent.com/' + repo + '/' + commit + '/'
    notice = tree.get('LICENSE')
    if not notice: raise ValueError('Current instrument dedication is missing')
    text = http.text(raw + 'LICENSE', 256*1024).lower()
    if not any(v in text for v in ('creativecommons.org/publicdomain/zero/1.0', 'cc0 1.0 universal')) or any(v in text for v in ('non-commercial use only', 'personal use only')):
        raise ValueError('Current instrument CC0 dedication is unverified')
    catalog = http.json(raw + 'catalog.json')
    collections = catalog.get('collections', [])
    if not isinstance(collections, list) or len(collections) > 32: raise ValueError('Instrument collection manifest exceeds navigation bound')
    rows = []; raw_members = 0; public_members = 0; pack_ids = []
    if key and not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', key): raise ValueError('Invalid instrument sample locator')
    for collection in collections:
        cid = collection.get('id', ''); folder = collection.get('path', '')
        if not re.fullmatch('[A-Za-z0-9_-]+', cid) or folder != 'systems/instruments/' + cid: continue
        if filters.get('_pack_key') and cid != filters['_pack_key'] or key and not key.startswith(cid + '/'): continue
        if folder + '/manifest.json' not in tree: continue
        manifest = http.json(raw + quote(folder, safe='/') + '/manifest.json')
        if manifest.get('id') != cid or manifest.get('category') != 'instruments': raise ValueError('Instrument membership metadata differs from its collection')
        samples = manifest.get('samples', [])
        if not isinstance(samples, list) or len(samples) > 10000: raise ValueError('Instrument sample manifest exceeds navigation bound')
        pack_ids.append(cid); raw_members += len(samples)
        known = set()
        for sample in samples:
            name = sample.get('file', ''); stem = PurePosixPath(name).stem
            if '/' in name or '\\' in name or not re.fullmatch('[A-Za-z0-9_-]+', stem) or stem in known: continue
            known.add(stem)
            locator = cid + '/' + stem
            if key and locator != key: continue
            if not key and locator <= after: continue
            available = [tree[p] for extension in ('wav', 'ogg') for p in (folder + '/' + extension + '/' + stem + '.' + extension,) if p in tree]
            if not available: continue
            public_members += 1
            originals = [{'url': raw + quote(v['path'], safe='/'), 'filename': PurePosixPath(v['path']).name,
                          'relative_path': v['path'], 'role': 'main' if i == 0 else 'variant', 'sha': v['sha'], 'bytes': v.get('size')}
                         for i, v in enumerate(available)]
            originals.append({'url': raw + 'LICENSE', 'filename': 'LICENSE', 'relative_path': 'LICENSE', 'role': 'license', 'sha': notice['sha'], 'bytes': notice.get('size')})
            a = item(source['id'], locator, collection.get('name', cid) + ' / ' + stem, 'audio', 'CC0-1.0',
                     'https://github.com/' + repo + '/blob/' + commit + '/LICENSE', 'Meta Creative Audio',
                     tags=collection.get('tags', []) + ['instrument multisample'], formats=[PurePosixPath(v['path']).suffix[1:] for v in available],
                     files=originals, description=collection.get('description', ''), pack=cid,
                     revision=__import__('hashlib').sha256(json.dumps([v['sha'] for v in available]).encode()).hexdigest())
            a['origin_identity'] = 'meta-open-sound:' + locator
            a['features'] = {'instrument': cid, 'quality_evidence': {'provider':'Meta Creative Audio','basis':'First-party professional multisample collection.','scope':'Local full audio validity/speech checks still required; publisher specification is separate from the delivered codec.'},
                             'publisher_master_specification': {k: manifest.get(k) for k in ('sample_rate', 'bit_depth', 'format')},
                             'available_original_formats': a['formats'],
                             'specification_scope': 'Advertised master format/depth does not certify public OGG payload precision. Actual delivered codec/sample rate is reported by audio inspection.'}
            a['reuse_scope'] = 'Current CC0 original files with exact publisher instrument-manifest membership. Missing WAV masters are not fabricated from advertised metadata.'
            rows.append(a)
    if key:
        if not rows: raise ValueError('Sample no longer has a current public file in its exact instrument manifest')
        return rows[0]
    result = window(rows, after, limit, filters)
    result['catalog'] = {'collections_in_scope': pack_ids, 'manifest_samples_in_scope': raw_members,
                         'public_sample_candidates_after_cursor': public_members, 'admitted_unique_assets': None,
                         'count_scope': 'Current manifest membership and actual public file candidates before local admission; not variants counted as separate sounds.'}
    return result
