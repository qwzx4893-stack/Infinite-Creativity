"""Resolve a selected component reference to independently public author code."""
import re
from urllib.parse import unquote,urlsplit
from .live import seal


def open_reference(library,reference):
    if not isinstance(reference,str) or not reference or len(reference)>1000:raise ValueError('Supply a bounded component reference')
    if reference.startswith('@'):
        author,sep,name=reference[1:].partition('/')
    else:
        parsed=urlsplit(reference)
        if parsed.scheme!='https' or parsed.hostname not in {'21st.dev','www.21st.dev'} or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError('Use a selected https://21st.dev/@author/components/name URL or @author/name')
        parts=unquote(parsed.path).strip('/').split('/')
        if len(parts)<2:raise ValueError('Component URL must identify an author and component')
        author=parts[0].removeprefix('@');name=parts[2] if len(parts)>=3 and parts[1]=='components' else parts[1];sep='/'
    if not sep or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',author) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',name):
        raise ValueError('Invalid author/component identifier')
    sources=[s for s in library.sources.values() if s.get('adapter')=='public-registry' and author.lower() in {a.lower().removeprefix('@') for a in s.get('reference_authors',[])}]
    if not sources:
        return {'state':'independent-author-route-not-configured','author':author,'component':name,
                'next_action':'discover_sources','query':author+' '+name,
                'scope':'No marketplace request or authenticated-access bypass. A public repository must establish its own current rights before delivery.'}
    failures=[]
    for source in sources:
        aid=seal('asset',{'source':source['id'],'key':name})
        try:
            asset=library.get(aid);card=library.card(asset)
            return {'state':'original-author-source-resolved','item':card,
                    'source':source['id'],'author_repository':source['repo'],
                    'provenance':'Independent author-published current original source; the supplied marketplace URL is a locator only and is not fetched.',
                    'next_action':'open_asset_package','storage':'No marketplace catalog, preview or original is copied into a saved inventory.'}
        except ValueError as error:failures.append({'source':source['id'],'reason':str(error)[:240]})
    return {'state':'original-author-item-unavailable','author':author,'component':name,'failures':failures}
