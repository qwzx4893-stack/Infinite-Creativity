"""Fresh, bounded HTTP reads. No disk cache, conditional request, or retained index."""
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener
from .content import validate_url, CONTENT_HOSTS
from .network import NoRedirect

class LiveHTTP:
    def __init__(self, hosts=(), max_requests=48):
        self.hosts=set(hosts)|CONTENT_HOSTS|{'api.polyhaven.com','www.blendkit.com','www.blenderkit.com','public.blenderkit.com','public.blendkit.com','ui.aceternity.com'}
        CONTENT_HOSTS.update(self.hosts)
        self.opener=build_opener(NoRedirect());self.requests=0;self.max_requests=max_requests
        self.started=time.monotonic();self.memo={}
    def read(self,url,max_bytes=16*1024*1024,accept='*/*'):
        # Memoization exists only inside this one MCP request, never across calls.
        if (url,max_bytes) in self.memo:return self.memo[url,max_bytes]
        current=url
        for _ in range(6):
            host=(urlsplit(current).hostname or '').lower()
            if host not in self.hosts:raise ValueError('Unconfigured source content host')
            CONTENT_HOSTS.add(host)
            validate_url(current)
            if self.requests>=self.max_requests or time.monotonic()-self.started>55:raise ValueError('Live request budget exhausted; continue with a narrower source or pack')
            headers={'User-Agent':'InfiniteCreativity/0.4 (+https://github.com/qwzx4893-stack/Infinite-Creativity)','Accept':accept,'Cache-Control':'no-cache','Pragma':'no-cache'}
            if host=='api.github.com' and os.environ.get('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
            if host in {'www.blendkit.com','www.blenderkit.com'} and os.environ.get('BLENDERKIT_TOKEN'):headers['Authorization']='Bearer '+os.environ['BLENDERKIT_TOKEN']
            self.requests+=1
            try:
                with self.opener.open(Request(current,headers=headers),timeout=12) as response:
                    data=response.read(max_bytes+1)
                    if len(data)>max_bytes:raise ValueError('Source response exceeds live memory budget')
                    self.memo[url,max_bytes]=data
                    return data
            except HTTPError as e:
                if e.code in {301,302,303,307,308} and e.headers.get('Location'):
                    current=urljoin(current,e.headers['Location']);continue
                if e.code==429:raise ValueError('Provider rate limit; Retry-After='+e.headers.get('Retry-After','unspecified')) from None
                if e.code in {401,403}:raise ValueError('Provider access denied or authentication required (HTTP '+str(e.code)+')') from None
                raise ValueError('Source HTTP '+str(e.code)) from None
            except (TimeoutError,URLError):raise ValueError('Source transport unavailable; no stored snapshot fallback') from None
        raise ValueError('Source redirect limit exceeded')
    def json(self,url):return json.loads(self.read(url,60*1024*1024,'application/json'))
    def text(self,url,max_bytes=8*1024*1024):return self.read(url,max_bytes).decode('utf-8-sig',errors='replace')
