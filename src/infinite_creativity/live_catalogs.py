"""Large public catalogs queried on demand; provider totals are never our inventory."""
import html
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urlsplit
from .policy import LICENSES


def plain(value):
    return ' '.join(html.unescape(re.sub('<[^>]*>', ' ', str(value or ''))).split())


def cc_license(url):
    url = str(url or '').replace('http://', 'https://', 1)
    if 'creativecommons.org/publicdomain/zero/1.0' in url:
        return 'CC0-1.0', url
    match = re.search(r'creativecommons.org/licenses/(by|by-sa)/(1\.0|2\.0|2\.5|3\.0|4\.0)', url)
    if match:
        return 'CC-' + match[1].upper() + '-' + match[2], url
    return 'unknown', url


def original(http, url, filename='', **extra):
    # Trust only a URL supplied by a configured API, with HTTPS/public DNS
    # validation still enforced on every read and every redirect.
    http.approve_content(url)
    return {'url': url, 'filename': filename or PurePosixPath(urlsplit(url).path).name,
            'role': 'main', **extra}


def openverse(http, s, f, after, limit, key=None):
    from .live_providers import item, matches
    medium = s.get('media', 'audio' if f.get('kind') == 'audio' or f.get('section', '').startswith('audio') else 'images')
    if key:
        medium, uid = key.split(':', 1)
        if medium not in {'images', 'audio'} or not re.fullmatch('[0-9a-f-]{36}', uid):
            raise ValueError('Invalid Openverse locator')
        data = {'results': [http.json(f'https://api.openverse.org/v1/{medium}/{uid}/')]}
        position = 0
    else:
        position = int(after or 0)
        params = {'q': f.get('query', '') or f.get('style', '') or s.get('default_query', 'design'),
                  'license': 'cc0,by,by-sa', 'license_type': 'commercial,modification',
                  'mature': 'false', 'filter_dead': 'true', 'page_size': 20, 'page': position // 20 + 1}
        if s.get('provider'): params['source'] = s['provider']
        data = http.json(f'https://api.openverse.org/v1/{medium}/?' + urlencode(params))
    rows = []; consumed = position % 20
    for x in data.get('results', [])[consumed if not key else 0:]:
        consumed += 1
        sensitivity=x.get('unstable__sensitivity')
        if x.get('mature') or (sensitivity in {'sensitive','mature'} if isinstance(sensitivity,str) else bool(sensitivity)): continue
        lic, evidence = cc_license(x.get('license_url'))
        url = x.get('url'); files = []
        if url and lic in LICENSES:
            try: files = [original(http, url, bytes=int(x['filesize']) if x.get('filesize') else None)]
            except ValueError: pass
        preview = x.get('thumbnail'); previews = []
        if preview:
            try: http.approve_content(preview); previews = [{'url': preview}]
            except ValueError: pass
        fmt=str(x.get('filetype') or PurePosixPath(urlsplit(url or '').path).suffix.lstrip('.')).lower().split('/')[-1]
        formats = [{'jpeg':'jpg','x-wav':'wav','mpeg':'mp3'}.get(fmt,fmt)]
        a = item(s['id'], medium + ':' + x['id'], x.get('title') or 'Untitled creative work',
                 'audio' if medium == 'audio' else 'illustration', lic, evidence, x.get('creator') or '',
                 [t.get('name', '') for t in x.get('tags', [])] + [x.get('source') or '', x.get('category') or ''],
                 formats, files=files, previews=previews, description=plain(x.get('attribution')),
                 pack=str((x.get('audio_set') or {}).get('foreign_landing_url') or ''), revision=x.get('indexed_on') or url or '')
        a['origin_url'] = x.get('foreign_landing_url') or ''
        a['features'] = {k: x.get(k) for k in ('width', 'height', 'duration', 'sample_rate', 'bit_rate')}
        a['provider_mature_flag'] = x.get('mature')
        a['reuse_scope'] = 'Original licence applies; retain attribution and share-alike obligations where declared. No endorsement or personality/trademark clearance implied.'
        # The upstream search is relevance-based; do not re-apply literal AND
        # matching and discard legitimate semantic matches from that search.
        if key or matches(a, {**f, 'query': ''}): rows.append(a)
        if not key and len(rows) == limit: break
    if key:
        if not rows: raise ValueError('Openverse item is unavailable or withheld by provider moderation')
        return rows[0]
    total = data.get('result_count', 0); next_position = (position // 20) * 20 + consumed
    return {'items': rows, 'next': str(next_position) if next_position < total else None,
            'total': None, 'scope': 'Current Openverse source window; reported search totals are not admitted-library counts'}


def commons(http, s, f, after, limit, key=None):
    from .live_providers import item, matches
    params = {'action': 'query', 'format': 'json', 'prop': 'imageinfo',
              'iiprop': 'url|extmetadata|sha1|mime|size', 'iiurlwidth': 512}
    if key:
        if not key.startswith('File:') or len(key) > 500: raise ValueError('Invalid Commons file locator')
        params['titles'] = key
    else:
        params.update(generator='search', gsrnamespace=6, gsrlimit=20,
                      gsrsearch=f.get('query') or f.get('style') or 'design illustration')
        if after: params.update(json.loads(after).get('continue', {}))
    data = http.json('https://commons.wikimedia.org/w/api.php?' + urlencode(params))
    pages = sorted(data.get('query', {}).get('pages', {}).values(), key=lambda x: x.get('index', 0))
    start = json.loads(after).get('skip', 0) if after and not key else 0
    rows = []; consumed = start
    for x in pages[start:]:
        consumed += 1
        if not x.get('imageinfo'): continue
        v = x['imageinfo'][0]; meta = v.get('extmetadata', {})
        get = lambda k: plain(meta.get(k, {}).get('value', ''))
        lic, evidence = cc_license(get('LicenseUrl'))
        # Commons may declare PD separately without a CC0 link; do not guess it.
        if lic not in LICENSES or get('Restrictions'): continue
        url = v.get('url', ''); mime = v.get('mime', '')
        kind = 'audio' if mime.startswith('audio/') else 'video' if mime.startswith('video/') else 'animation-2d' if mime == 'image/gif' else 'illustration'
        file = original(http, url, bytes=v.get('size'), sha=v.get('sha1'), sha_scope='mediawiki-sha1-not-git-blob')
        # MediaWiki SHA1 is not a Git object hash; don't pass it as Git integrity.
        file.pop('sha', None)
        previews = [{'url': v['thumburl']}] if v.get('thumburl') else []
        for preview in previews: http.approve_content(preview['url'])
        a = item(s['id'], x['title'], get('ObjectName') or x['title'][5:], kind, lic, evidence, get('Artist'),
                 get('Categories').split('|'), [PurePosixPath(urlsplit(url).path).suffix.lstrip('.').lower()],
                 files=[file], previews=previews, description=get('ImageDescription'), revision=v.get('sha1', ''))
        a['origin_url'] = v.get('descriptionurl', '')
        a['features'] = {'width': v.get('width'), 'height': v.get('height'), 'provider_assessments': get('Assessments')}
        a['reuse_scope'] = 'Current file licence applies, including attribution/share-alike if declared.'
        if key or matches(a, {**f, 'query': ''}): rows.append(a)
        if not key and len(rows) == limit: break
    if key:
        if not rows: raise ValueError('Commons file is unavailable or lacks supported unrestricted/attribution rights')
        return rows[0]
    previous = json.loads(after).get('continue', {}) if after else {}
    next_position = {'continue': previous, 'skip': consumed} if consumed < len(pages) else {'continue': data['continue']} if data.get('continue') else None
    return {'items': rows, 'next': json.dumps(next_position) if next_position is not None else None,
            'total': None, 'scope': 'Current Commons file search with per-file rights; no global inventory assertion'}


def artic(http, s, f, after, limit, key=None):
    from .live_providers import item, matches
    fields = 'id,title,is_public_domain,image_id,artist_display,artwork_type_title,date_display,description,style_title'
    base = 'https://api.artic.edu/api/v1/artworks'
    if key:
        if not key.isdigit(): raise ValueError('Invalid artwork ID')
        data = http.json(base + '/' + key + '?' + urlencode({'fields': fields})); raw = [data['data']]; consumed = 0
    else:
        position = int(after or 0); consumed = position % 20
        params = {'q': f.get('query') or f.get('style') or 'landscape', 'page': position // 20 + 1, 'limit': 20,
                  'fields': fields.split(','), 'query': {'term': {'is_public_domain': True}}}
        data = http.json(base + '/search?' + urlencode({'params':json.dumps(params,separators=(',',':'))})); raw = data.get('data', [])
    rows = []
    for x in raw[consumed if not key else 0:]:
        consumed += 1
        if not x.get('is_public_domain') or not x.get('image_id'): continue
        root = 'https://www.artic.edu/iiif/2/' + quote(x['image_id'], safe='')
        url = root + '/full/max/0/default.jpg'; preview = root + '/full/512,/0/default.jpg'
        a = item(s['id'], str(x['id']), x['title'], 'illustration', 'CC0-1.0',
                 'https://www.artic.edu/open-access/open-access-images', x.get('artist_display', ''),
                 [x.get('artwork_type_title') or '', x.get('style_title') or '', x.get('date_display') or ''], ['jpg'],
                 files=[original(http, url, str(x['id']) + '.jpg')], previews=[{'url': preview}],
                 description=plain(x.get('description')), revision=x['image_id'])
        a['origin_url'] = 'https://www.artic.edu/artworks/' + str(x['id'])
        a['features']={'metadata_rights':{'description':'CC-BY-4.0','other_metadata':'CC0-1.0'},'image_public_domain':True}
        if key or matches(a, {**f, 'query': ''}): rows.append(a)
        if not key and len(rows) == limit: break
    if key:
        if not rows: raise ValueError('Artwork image is not currently public domain')
        return rows[0]
    next_position = (position // 20) * 20 + consumed
    cap=min(data.get('pagination', {}).get('total', 0),10000)
    return {'items': rows, 'next': str(next_position) if next_position < cap else None,
            'total': None, 'scope': 'Current Art Institute public-domain artwork images; provider search cap is 10,000; refine query beyond this window'}


def sketchfab(http, s, f, after, limit, key=None):
    from .live_providers import item, matches
    if key:
        if not re.fullmatch('[0-9a-f]{32}', key): raise ValueError('Invalid Sketchfab model locator')
        data = {'results': [http.json('https://api.sketchfab.com/v3/models/' + key)]}; start = 0
    else:
        cursor = json.loads(after) if after else {'cursor': '', 'skip': 0}; start = cursor['skip']
        params = {'type': 'models', 'downloadable': 'true', 'q': f.get('query') or f.get('style') or 'stylized', 'count': 20}
        if cursor['cursor']: params['cursor'] = cursor['cursor']
        data = http.json('https://api.sketchfab.com/v3/search?' + urlencode(params))
    rows = []; consumed = start
    for x in data.get('results', [])[start:]:
        consumed += 1
        if x.get('isRestricted') or x.get('isAgeRestricted'): continue
        licence = x.get('license') or {}; lic, evidence = cc_license(licence.get('url'))
        if lic == 'unknown' and licence.get('label') == 'CC Attribution': lic, evidence = 'CC-BY-4.0', 'https://creativecommons.org/licenses/by/4.0/'
        if lic == 'unknown' and licence.get('label') == 'CC0 Public Domain': lic, evidence = 'CC0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'
        previews = sorted(x.get('thumbnails', {}).get('images', []), key=lambda p: abs(p.get('width', 512) - 512))[:1]
        files = []
        import os
        if key and os.environ.get('SKETCHFAB_TOKEN') and x.get('isDownloadable') and lic in LICENSES:
            exports = http.json('https://api.sketchfab.com/v3/models/' + key + '/download')
            for fmt, v in exports.items():
                if isinstance(v, dict) and v.get('url'): files.append(original(http, v['url'], key + '-' + fmt + '.zip', bytes=v.get('size')))
        a = item(s['id'], x['uid'], x['name'], 'model-3d', lic, evidence, (x.get('user') or {}).get('displayName', ''),
                 [t.get('name', '') for t in x.get('tags', [])], ['glb', 'gltf', 'usdz'], files=files,
                 previews=previews, description=plain(x.get('description')), revision=x.get('publishedAt', ''), reference_preview=True)
        a['original_access'] = 'official-authenticated-download' if files else 'SKETCHFAB_TOKEN-required-for-originals'
        a['features'] = {k: x.get(k) for k in ('vertexCount', 'faceCount', 'animationCount', 'likeCount')}
        a['origin_url'] = x.get('viewerUrl') or 'https://sketchfab.com/3d-models/' + x['uid']
        if key or matches(a, {**f, 'query': ''}): rows.append(a)
        if not key and len(rows) == limit: break
    if key:
        if not rows: raise ValueError('Model unavailable or provider flagged restricted content')
        return rows[0]
    next_cursor = (data.get('cursors') or {}).get('next')
    position = {'cursor': cursor['cursor'], 'skip': consumed} if consumed < len(data.get('results', [])) else {'cursor': next_cursor, 'skip': 0} if next_cursor else None
    return {'items': rows, 'next': json.dumps(position) if position is not None else None, 'total': None,
            'scope': 'Current public downloadable-model search; original download requires official account token'}
