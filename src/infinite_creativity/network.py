import gzip
import hashlib
import json
import os
import time
import sqlite3
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def icon_inventory(stream):
    """Extract only icon names and license evidence from large official exports."""
    import ijson
    class Bounded:
        def __init__(self): self.total=0
        def read(self,size=-1):
            data=stream.read(size)
            self.total+=len(data)
            if self.total>512*1024*1024:
                raise ValueError('Streaming export exceeded 512 MiB limit')
            return data
    names=set(); hidden=set(); license={}; prefix_value=''
    for prefix,event,value in ijson.parse(Bounded()):
        if prefix=='icons' and event=='map_key': names.add(value)
        elif prefix.startswith('icons.') and prefix.endswith('.hidden') and event=='boolean' and value:
            hidden.add(prefix[len('icons.'):-len('.hidden')])
        elif prefix.startswith('info.license.') and event=='string':
            license[prefix[len('info.license.'):]]=value
        elif prefix=='prefix' and event=='string': prefix_value=value
    return {'prefix':prefix_value,'icons':{name:{} for name in sorted(names-hidden)},'info':{'license':license}}

class Fetcher:
    def __init__(self, cache="state/http"):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last = {}
        self.opener = build_opener(NoRedirect())

    def search_gate(self):
        """Share search pacing between independent refresh/discovery processes."""
        with sqlite3.connect(self.cache/'search-pacing.sqlite',timeout=30) as db:
            db.execute('CREATE TABLE IF NOT EXISTS pacing(id INTEGER PRIMARY KEY,stamp REAL)')
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT stamp FROM pacing WHERE id=1').fetchone()
            if row: time.sleep(max(0,2.2-(time.time()-row[0])))
            db.execute('INSERT OR REPLACE INTO pacing VALUES (1,?)',(time.time(),))

    def json(self, url):
        host = urlsplit(url).hostname
        if urlsplit(url).scheme != "https" or host not in {"api.github.com", "raw.githubusercontent.com", "api.iconify.design", "api.polyhaven.com", "ambientcg.com", "fuel.gazebosim.org","zenodo.org","huggingface.co"}:
            raise ValueError("Unapproved metadata endpoint")
        key = hashlib.sha256(url.encode()).hexdigest()
        body_path, meta_path = self.cache / (key + ".json.gz"), self.cache / (key + ".meta.json")
        if __import__('re').search(r'/git/(blobs|trees)/[0-9a-f]{40}(?:\?|$)',url) and body_path.exists():
            return json.loads(gzip.decompress(body_path.read_bytes()))
        headers = {"User-Agent": "InfiniteCreativity/0.1 (+https://github.com/qwzx4893-stack/Infinite-Creativity)", "Accept": "application/json"}
        if host == "api.github.com" and os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        if meta_path.exists() and body_path.exists():
            meta = json.loads(meta_path.read_text())
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("modified"):
                headers["If-Modified-Since"] = meta["modified"]
        interval = 2.2 if "/search/" in url else .15
        for attempt in range(3):
            if '/search/' in url: self.search_gate()
            time.sleep(max(0, interval - (time.monotonic() - self.last.get(host, 0))))
            self.last[host] = time.monotonic()
            try:
                with self.opener.open(Request(url, headers=headers), timeout=45) as response:
                    if url.endswith('/iconify/icon-sets/master/json/fluent-emoji.json'):
                        data=icon_inventory(response)
                        body=json.dumps(data).encode()
                    else:
                        body = response.read(60 * 1024 * 1024 + 1)
                        if len(body) > 60 * 1024 * 1024:
                            raise ValueError("Metadata response too large")
                        data = json.loads(body)
                    tmp = body_path.with_suffix(".tmp")
                    tmp.write_bytes(gzip.compress(body))
                    tmp.replace(body_path)
                    meta_path.write_text(json.dumps({"etag": response.headers.get("ETag"), "modified": response.headers.get("Last-Modified")}))
                    return data
            except HTTPError as e:
                if e.code == 304 and body_path.exists():
                    return json.loads(gzip.decompress(body_path.read_bytes()))
                if e.code == 429:
                    raise RuntimeError(f"HTTP 429 from {host}; defer until provider Retry-After={e.headers.get('Retry-After','unspecified')}") from None
                if e.code in {500, 502, 503, 504} and attempt < 2:
                    delay = min(30, int(e.headers.get("Retry-After", "3")) if e.headers.get("Retry-After", "3").isdigit() else 3)
                    time.sleep(max(delay, 2 ** attempt))
                    continue
                raise RuntimeError(f"HTTP {e.code} from {host}") from None
            except (TimeoutError, URLError) as e:
                if attempt == 2: raise RuntimeError(f'Metadata transport unavailable from {host}: {type(e).__name__}') from None
                time.sleep(2 ** attempt)
        raise RuntimeError("Retry budget exhausted")
