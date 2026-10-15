"""Bounded live navigation of large public collections; no retained item index."""
import hashlib
import io
import gzip
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode, urlsplit
from .live_catalogs import cc_license, original, plain
from .policy import LICENSES, acceptable, review_terms

VIEWER = 'https://datasets-server.huggingface.co/'
OBJAVERSE = 'https://huggingface.co/datasets/allenai/objaverse/resolve/main/'
PD_MARK = 'LicenseRef-Public-Domain-Mark-1.0'


def position(value, maximum=100_000_000):
    if isinstance(value, bool) or not re.fullmatch(r'\d{1,9}', str(value)):
        raise ValueError('Catalog position must be a nonnegative integer')
    value = int(value)
    if value > maximum: raise ValueError('Catalog position exceeds the navigation bound')
    return value


def pd3m(http, source, filters, after, limit, key=None):
    from .live_providers import item, matches
    if key:
        match = re.fullmatch(r'(\d{1,9}):([0-9a-f]{32})', key)
        if not match: raise ValueError('Invalid PD3M row locator')
        offset = position(match[1]); length = 1
    else:
        offset = position(after or filters.get('catalog_offset', 0))
        length = 100
    params = {'dataset': 'Spawning/PD3M', 'config': 'default', 'split': 'train', 'offset': offset, 'length': length}
    data = http.json(VIEWER + 'rows?' + urlencode(params))
    raw = data.get('rows', [])
    total = position(data.get('num_rows_total', 0))
    if len(raw) > length: raise ValueError('Provider exceeded the requested catalog window')
    result = []; consumed = offset; excluded = {}
    for index, record in enumerate(raw):
        if record.get('row_idx') != offset + index: raise ValueError('Non-contiguous upstream row window')
        consumed += 1; x = record.get('row', {})
        uid = str(x.get('id', '')); url = str(x.get('url', '')); digest = str(x.get('hash', ''))
        if record.get('truncated_cells') or not re.fullmatch('[0-9a-f]{32}', uid):
            excluded['incomplete-record'] = excluded.get('incomplete-record', 0) + 1; continue
        if key and uid != match[2]: raise ValueError('Dataset row moved; open a fresh catalog window')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'pd12m.s3.us-west-2.amazonaws.com' or not re.fullmatch(r'/images/[0-9a-f-]{36}\.(?:jpeg|jpg|png|webp)', parsed.path) or parsed.query or parsed.fragment:
            excluded['unapproved-image-route'] = excluded.get('unapproved-image-route', 0) + 1; continue
        licence, evidence = cc_license(x.get('license'))
        if str(x.get('license', '')).replace('http://', 'https://', 1) in {'https://creativecommons.org/publicdomain/mark/1.0/', 'https://creativecommons.org/publicdomain/mark/1.0'}:
            licence = PD_MARK; evidence = 'https://creativecommons.org/publicdomain/mark/1.0/'
        if licence not in {'CC0-1.0', PD_MARK} or not re.fullmatch('[0-9a-f]{32}', digest):
            excluded['rights-or-checksum-unverified'] = excluded.get('rights-or-checksum-unverified', 0) + 1; continue
        width, height = x.get('width'), x.get('height')
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 512 for v in (width, height)) or max(width, height) < 1024:
            excluded['below-photo-art-resolution-floor'] = excluded.get('below-photo-art-resolution-floor', 0) + 1; continue
        caption = plain(x.get('caption'))
        if not caption or not acceptable(caption) or review_terms(caption):
            excluded['content-metadata'] = excluded.get('content-metadata', 0) + 1; continue
        photo = bool(re.search(r'\b(photo|photograph|photography)\b', caption, re.I))
        title = re.sub(r'^The image shows\s+', '', caption, flags=re.I)[:180]
        a = item(source['id'], str(record['row_idx']) + ':' + uid, title, 'image' if photo else 'illustration',
                 licence, evidence, tags=['photography' if photo else 'artwork', 'publisher-aesthetic-subset', str(x.get('source', ''))],
                 formats=[parsed.path.rsplit('.', 1)[-1]], files=[original(http, url, uid + '.' + parsed.path.rsplit('.', 1)[-1], md5=digest)],
                 description=caption, revision=digest)
        a['origin_identity'] = 'pd12m:' + uid
        a['origin_url'] = 'https://huggingface.co/datasets/Spawning/PD3M'
        a['features'] = {'width': width, 'height': height, 'metadata_license': 'CDLA-Permissive-2.0',
                         'quality_evidence': {'publisher': 'Spawning/PD3M', 'basis': 'Publisher-selected high aesthetic score subset; minimum short edge 512 / long edge 1024 pixels. Not independent craft certification.'},
                         'declared_technical': {'width': width, 'height': height}}
        a['reuse_scope'] = 'Image-specific public-domain designation or CC0, distinct from the metadata licence. Public Domain Mark is a designation, not a CC0 dedication. Publisher-hosted copy; no claim of source-master resolution or separate personality/trademark clearance.'
        if key or matches(a, filters): result.append(a)
        if not key and len(result) >= limit: break
    if key:
        if not result: raise ValueError('Current PD3M row fails rights, content or resolution checks')
        return result[0]
    return {'items': result, 'next': str(consumed) if consumed < total and raw else None, 'total': None,
            'catalog': {'provider_rows': total, 'admitted_unique_assets': None, 'position': offset, 'next_position': consumed,
                        'excluded_in_window': excluded, 'query_scope': 'Literal caption/style/category matching in this bounded 100-row window, not global full-text search. Jump offsets with browse_asset_catalog.',
                        'provider_partial': bool(data.get('partial'))},
            'scope': 'Fresh PD3M rows and individual image rights. Publisher aesthetic selection precedes local original-image screening; totals are upstream rows, not accepted assets.'}


def shard_rows(http, shard):
    if not re.fullmatch(r'\d{3}-\d{3}', shard): raise ValueError('Invalid Objaverse partition')
    body = http.read(OBJAVERSE + 'metadata/' + shard + '.json.gz', 8*1024*1024)
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
        decoded = stream.read(48*1024*1024 + 1)
    if len(decoded) > 48*1024*1024: raise ValueError('Objaverse metadata decompression budget exceeded')
    data = json.loads(decoded)
    if not isinstance(data, dict) or len(data) > 10000: raise ValueError('Invalid bounded Objaverse partition')
    return data


def objaverse(http, source, filters, after, limit, key=None):
    from .live_providers import item, matches
    if key:
        match = re.fullmatch(r'(\d{3}-\d{3}):([0-9a-f]{32})', key)
        if not match: raise ValueError('Invalid Objaverse object locator')
        shard, uid = match.groups(); records = shard_rows(http, shard)
        if uid not in records: raise ValueError('Object no longer belongs to its upstream partition')
        raw = [(uid, records[uid])]; start = 0; partition = None; partitions = []
    else:
        partition, start = (map(position, after.split(':')) if after else
                            (position(filters.get('catalog_partition', 0)), position(filters.get('catalog_offset', 0))))
        listing = http.json('https://huggingface.co/api/datasets/allenai/objaverse/tree/main/metadata?limit=200')
        partitions = sorted({x['path'].split('/')[1][:-8] for x in listing if x.get('type') == 'file' and re.fullmatch(r'metadata/\d{3}-\d{3}\.json\.gz', x.get('path', ''))})
        if partition >= len(partitions): raise ValueError('Choose a partition within the current provider listing')
        shard = partitions[partition]; records = shard_rows(http, shard); raw = sorted(records.items())
        if start > len(raw): raise ValueError('Offset exceeds this partition; choose another partition')
    candidates = []; consumed = start; excluded = {}; errors = []
    for uid, archived in raw[start:] if not key else raw:
        consumed += 1
        text = plain(archived.get('name')) + ' ' + plain(archived.get('description')) + ' ' + ' '.join(t.get('name', '') for t in archived.get('tags', []))
        if not re.fullmatch('[0-9a-f]{32}', uid) or archived.get('uid') != uid or archived.get('license') not in {'cc0', 'by', 'by-sa'} or archived.get('isAgeRestricted') is not False:
            excluded['rights-or-age-restricted'] = excluded.get('rights-or-age-restricted', 0) + 1; continue
        if not acceptable(text) or review_terms(text):
            excluded['content-metadata'] = excluded.get('content-metadata', 0) + 1; continue
        if not archived.get('staffpickedAt') and int(archived.get('likeCount') or 0) < 25:
            excluded['no-curation-signal'] = excluded.get('no-curation-signal', 0) + 1; continue
        preliminary = item(source['id'], shard + ':' + uid, plain(archived.get('name')), 'animation-3d' if archived.get('animationCount') else 'model-3d', 'CC0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', tags=[t.get('name', '') for t in archived.get('tags', [])], formats=['glb'], description=plain(archived.get('description')))
        if not key and not matches(preliminary, filters): continue
        candidates.append((uid, archived))
        if len(candidates) >= min(limit, 6): break
    def current(pair):
        uid, archived = pair
        try:
            data = http.json('https://api.sketchfab.com/v3/models/' + uid)
            licence, evidence = cc_license((data.get('license') or {}).get('url'))
            if data.get('uid') != uid or data.get('isAgeRestricted') is not False or data.get('isDownloadable') is not True or licence not in LICENSES or (data.get('license') or {}).get('slug') != archived['license']:
                raise ValueError('Current model rights/availability/age policy differs or is unsupported')
            if (data.get('user') or {}).get('uid') != (archived.get('user') or {}).get('uid'):
                raise ValueError('Current creator differs from the archived original')
            if not data.get('staffpickedAt') and int(data.get('likeCount') or 0) < 25:
                raise ValueError('Current model no longer has the configured curation signal')
            current_text = plain(data.get('name')) + ' ' + plain(data.get('description')) + ' ' + ' '.join(t.get('name', '') for t in data.get('tags', []))
            if not acceptable(current_text) or review_terms(current_text): raise ValueError('Current model content metadata is excluded')
            archive = (archived.get('archives') or {}).get('glb') or {}
            if int(archived.get('faceCount') or 0) < 1 or int(archived.get('vertexCount') or 0) < 3:
                raise ValueError('No declared usable mesh geometry')
            url = OBJAVERSE + 'glbs/' + shard + '/' + uid + '.glb'
            tags = [t.get('name', '') for t in archived.get('tags', [])] + [t.get('name', '') for t in archived.get('categories', [])]
            author = (archived.get('user') or {}).get('displayName') or (archived.get('user') or {}).get('username') or ''
            a = item(source['id'], shard + ':' + uid, plain(archived.get('name')), preliminary_kind(archived), licence, evidence, author, tags, ['glb'],
                     files=[original(http, url, uid + '.glb')], description=plain(archived.get('description')),
                     revision=hashlib.sha256(json.dumps(archived, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
            a['origin_identity'] = 'sketchfab:' + uid; a['origin_url'] = 'https://sketchfab.com/3d-models/' + uid
            a['features'] = {'quality_evidence': {'current_staff_pick': bool(data.get('staffpickedAt')), 'current_likes': data.get('likeCount'), 'minimum_likes_without_staff_pick': 25, 'scope': 'Public curation/popularity signal, not proof of artistic craft.'},
                             'declared_technical': {'triangles': archived.get('faceCount'), 'vertices': archived.get('vertexCount'), 'animation_count': archived.get('animationCount'), 'texture_count': archive.get('textureCount')},
                             'provenance': 'Objaverse archived original, with current source-model creator/licence/availability rechecked; source-model edits are not claimed to update the archived GLB.'}
            a['reuse_scope'] = 'Original mirrored by AllenAI Objaverse under its per-model Creative Commons licence, with required creator credit/share-alike. Dataset licence does not replace object rights. Current Sketchfab metadata is checked, not its authenticated download API.'
            return a, None
        except Exception as e: return None, {'key': shard + ':' + uid, 'reason': str(e)[:240]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        checked = list(pool.map(current, candidates))
    rows = [a for a, error in checked if a]; errors = [e for a, e in checked if e]
    if key:
        if not rows: raise ValueError(errors[0]['reason'] if errors else 'Object lacks the configured curation/rights signal')
        return rows[0]
    next_position = str(partition) + ':' + str(consumed) if consumed < len(raw) else str(partition+1) + ':0' if partition+1 < len(partitions) else None
    return {'items': rows, 'next': next_position, 'total': None, 'item_errors': errors,
            'catalog': {'provider_partition_count': len(partitions), 'partition': partition, 'partition_id': shard,
                        'partition_rows': len(raw), 'next_position_in_partition': consumed, 'partition_listing_complete': len(listing) < 200,
                        'excluded_in_window': excluded, 'admitted_unique_assets': None,
                        'query_scope': 'Current annotation partition, not a global search, then current per-model source verification. Jump partitions with browse_asset_catalog.'},
            'scope': 'Curated Objaverse 1.0 GLBs only, excluding noncommercial/no-derivatives/missing rights and age-restricted records; no claim to all Objaverse-XL objects or a filtered total.'}


def preliminary_kind(record):
    return 'animation-3d' if record.get('animationCount') else 'model-3d'
