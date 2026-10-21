"""Fresh, bounded HTTP reads. No disk cache, conditional request, or retained index."""
import json
import os
import time
import threading
from urllib.parse import urlsplit, urljoin
from concurrent.futures import Future
import httpx
from .content import validate_url, CONTENT_HOSTS
from .request_scope import checkpoint
from .public_transport import PublicTransport

class LiveHTTP:
    def __init__(self, hosts=(), max_requests=48):
        self.hosts=set(hosts)|CONTENT_HOSTS|{'api.polyhaven.com','www.blendkit.com','www.blenderkit.com','public.blenderkit.com','public.blendkit.com','ui.aceternity.com'}
        self.requests=0;self.max_requests=max_requests
        self.started=time.monotonic();self.memo={};self.pending={};self.memo_bytes=0;self.network_bytes=0;self.memo_hits=0
        self.client=None;self.closed=False
        self.lock=threading.Lock()
    def close(self):
        with self.lock:
            client=self.client;self.client=None;self.closed=True;self.memo.clear();self.memo_bytes=0
        if client:client.close()
    def metrics(self):return {'http_requests':self.requests,'http_decoded_bytes':self.network_bytes,'request_memo_hits':self.memo_hits,'elapsed_seconds':round(time.monotonic()-self.started,3),'scope':'This LiveHTTP scope, including previews and fast-review originals. Parallel child scopes and selected-file staging have separate transport/budgets. No metrics or item data retained.'}
    def approve_content(self,url):
        """A configured upstream API supplied this URL; public HTTPS is still required."""
        host=(urlsplit(url).hostname or '').lower()
        if not host or len(host)>253:raise ValueError('Invalid provider content host')
        try:validate_url(url,hosts={host})
        except Exception:
            raise ValueError('Provider content URL is not public HTTPS') from None
        self.hosts.add(host)
    def read(self,url,max_bytes=16*1024*1024,accept='*/*'):
        checkpoint()
        if isinstance(max_bytes,bool) or not isinstance(max_bytes,int) or not 0<max_bytes<=128*1024*1024:raise ValueError('Invalid live response byte budget')
        key=(url,max_bytes,accept)
        with self.lock:
            if self.closed:raise ValueError('Live HTTP request scope is closed')
            if key in self.memo:self.memo_hits+=1;return self.memo[key]
            owner=key not in self.pending
            future=self.pending.setdefault(key,Future())
            if self.client is None:self.client=httpx.Client(transport=PublicTransport(),follow_redirects=False,trust_env=False,timeout=httpx.Timeout(12,connect=6,pool=6),limits=httpx.Limits(max_connections=8,max_keepalive_connections=8))
        if not owner:
            while True:
                checkpoint()
                try:return future.result(timeout=.05)
                except TimeoutError:
                    if future.done():raise
        try:
            data=self._read(url,max_bytes,accept)
            with self.lock:
                if self.memo_bytes+len(data)<=96*1024*1024:self.memo[key]=data;self.memo_bytes+=len(data)
            future.set_result(data);return data
        except BaseException as e:future.set_exception(e);raise
        finally:
            with self.lock:self.pending.pop(key,None)
    def _read(self,url,max_bytes,accept):
        current=url
        for _ in range(6):
            host=(urlsplit(current).hostname or '').lower()
            if host not in self.hosts and urlsplit(url).hostname=='archive.org' and host.endswith('.archive.org'):
                self.approve_content(current)
            if host not in self.hosts:raise ValueError('Unconfigured source content host')
            validate_url(current,hosts=self.hosts)
            checkpoint(requests=1)
            if self.requests>=self.max_requests or time.monotonic()-self.started>55:raise ValueError('Live request budget exhausted; continue with a narrower source or pack')
            headers={'User-Agent':'InfiniteCreativity/0.10 (+https://github.com/qwzx4893-stack/Infinite-Creativity)','Accept':accept,'Cache-Control':'no-cache','Pragma':'no-cache'}
            if host=='api.github.com' and os.environ.get('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
            if host in {'www.blendkit.com','www.blenderkit.com'} and os.environ.get('BLENDERKIT_TOKEN'):headers['Authorization']='Bearer '+os.environ['BLENDERKIT_TOKEN']
            with self.lock:
                if self.requests>=self.max_requests:raise ValueError('Live request budget exhausted')
                self.requests+=1
            try:
                with self.client.stream('GET',current,headers=headers) as response:
                    status=response.status_code
                    if status in {301,302,303,307,308} and response.headers.get('Location'):
                        current=urljoin(current,response.headers['Location']);continue
                    if status==429:raise ValueError('Provider rate limit; Retry-After='+response.headers.get('Retry-After','unspecified'))
                    if status in {401,403}:raise ValueError('Provider access denied or authentication required (HTTP '+str(status)+')')
                    if status!=200:raise ValueError('Source HTTP '+str(status))
                    data=bytearray()
                    for block in response.iter_bytes(64*1024):
                        checkpoint(received_bytes=len(block))
                        if time.monotonic()-self.started>55:raise ValueError('Live request time budget exhausted')
                        if len(data)+len(block)>max_bytes:raise ValueError('Source response exceeds live memory budget')
                        data.extend(block)
                    with self.lock:self.network_bytes+=len(data)
                    return bytes(data)
            except (httpx.TransportError,TimeoutError,OSError):raise ValueError('Source transport unavailable; no stored snapshot fallback') from None
        raise ValueError('Source redirect limit exceeded')
    def json(self,url):return json.loads(self.read(url,60*1024*1024,'application/json'))
    def text(self,url,max_bytes=8*1024*1024):return self.read(url,max_bytes).decode('utf-8-sig',errors='replace')
