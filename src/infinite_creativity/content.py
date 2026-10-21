"""Bounded, cache-backed original content access. No remote code execution."""
import hashlib
import ipaddress
import json
import mimetypes
import socket
import uuid
import io
import re
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit,urljoin
from urllib.request import Request,build_opener
from .network import NoRedirect

CONTENT_HOSTS={'raw.githubusercontent.com','api.iconify.design','cdn.polyhaven.com','dl.polyhaven.org','polyhaven.com','ambientcg.com','downloads.ambientcg.com','api.github.com','fuel.gazebosim.org','storage.googleapis.com','codeload.github.com','kenney.nl','quaternius.com','drive.google.com','drive.usercontent.google.com','zenodo.org','download.blender.org','www.blender.org','studio.blender.org','huggingface.co'}
HOST_SUFFIXES=('.polyhaven.com','.polyhaven.org','.ambientcg.com','.backblazeb2.com','.githubusercontent.com','.blender.org','.archive.org')
CONTENT_HOSTS.add('freshluts.com')
# A single documented public provider uses this TLS port. Never accept arbitrary
# ports supplied by asset metadata or redirects.
CONTENT_PORTS={('lazytextures.net',3000)}

class RangeUnsupported(ValueError):
    pass

def validate_url(url,resolve_dns=True,hosts=()):
    p=urlsplit(url)
    host=(p.hostname or '').lower()
    if p.scheme!='https' or p.username or p.password or (p.port not in (None,443) and (host,p.port) not in CONTENT_PORTS): raise ValueError('Only public HTTPS content is allowed')
    if host not in CONTENT_HOSTS and host not in hosts and not any(host.endswith(s) for s in HOST_SUFFIXES): raise ValueError('Content host is not approved')
    if resolve_dns:
        for item in socket.getaddrinfo(host,p.port or 443,type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(item[4][0]).is_global: raise ValueError('Private network content is prohibited')
    return url

class ContentCache:
    def __init__(self,root,hosts=()):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        from .public_transport import ContentOpener
        self.hosts=hosts
        self.opener=ContentOpener()
    def request_headers(self,url):
        return {'User-Agent':'InfiniteCreativity/0.12','Accept':'*/*','Accept-Encoding':'identity'}

    def range(self,url,start,length):
        """Read a verified HTTP byte range; never silently download a whole archive."""
        if start<0 or not 1<=length<=128*1024*1024: raise ValueError('Invalid HTTP range budget')
        current=url
        for _ in range(6):
            validate_url(current,hosts=self.hosts)
            try:
                response=self.opener.open(Request(current,headers={**self.request_headers(current),'Accept-Encoding':'identity','Range':f'bytes={start}-{start+length-1}'}),timeout=12)
            except HTTPError as e:
                if e.code in (301,302,303,307,308) and e.headers.get('Location'):
                    current=urljoin(current,e.headers['Location']); continue
                raise RuntimeError(f'Range HTTP {e.code} from {urlsplit(current).hostname}') from None
            with response:
                match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                if response.status==200:raise RangeUnsupported('Provider does not support bounded archive ranges or original ranges')
                if response.status!=206 or not match: raise ValueError('Provider returned an invalid bounded original range')
                first,last,total=map(int,match.groups())
                if first!=start or last!=min(start+length,total)-1 or total<=last: raise ValueError('Invalid provider content range')
                body=response.read(length+1)
                if len(body)!=last-first+1: raise ValueError('Incomplete or oversized provider range')
                return body,total
        raise ValueError('Too many content redirects')

    def remote_zip(self,url):
        return zipfile.ZipFile(RangeZip(self,url))

    def multipart_zip(self,parts):
        from .multipart import MultipartZip
        return MultipartZip(self,parts)

    def store(self,body,filename,mime='application/octet-stream'):
        digest=hashlib.sha256(body).hexdigest()
        extension=Path(filename).suffix.lower()
        if not extension or len(extension)>10 or not extension[1:].isalnum(): extension='.bin'
        path=self.root/(digest+extension)
        if not path.exists():
            temp=self.root/(uuid.uuid4().hex+'.part'); temp.write_bytes(body); temp.replace(path)
        return {'path':str(path.resolve()),'sha256':digest,'bytes':len(body),'mime':mime,'filename':Path(filename).name}

    def fetch(self,url,filename='',max_bytes=128*1024*1024,expected_sha256=None,cache_revision=''):
        if not 1<=max_bytes<=512*1024*1024: raise ValueError('Content byte budget must be 1..512 MiB')
        validate_url(url,resolve_dns=False,hosts=self.hosts)
        key=hashlib.sha256((url+('|' +cache_revision if cache_revision else '')).encode()).hexdigest()
        info_path=self.root/(key+'.receipt.json')
        if info_path.exists():
            result=json.loads(info_path.read_text(encoding='utf-8'))
            path=Path(result['path']).resolve()
            if path.parent==self.root.resolve() and path.is_file():
                if result['bytes']>max_bytes: raise ValueError('Cached content exceeds requested budget')
                if hashlib.sha256(path.read_bytes()).hexdigest()==result['sha256']:
                    if not expected_sha256 or result['sha256']==expected_sha256: return result
        current=url
        response=None
        for _ in range(6):
            validate_url(current,hosts=self.hosts)
            try:
                response=self.opener.open(Request(current,headers=self.request_headers(current)),timeout=12)
                break
            except HTTPError as e:
                if e.code in (301,302,303,307,308) and e.headers.get('Location'):
                    current=urljoin(current,e.headers['Location']); continue
                raise RuntimeError(f'Content HTTP {e.code} from {urlsplit(current).hostname}') from None
        if response is None: raise ValueError('Too many content redirects')
        temp=self.root/(uuid.uuid4().hex+'.part')
        digest=hashlib.sha256(); total=0
        try:
            with response,temp.open('wb') as out:
                if int(response.headers.get('Content-Length','0'))>max_bytes: raise ValueError('Content exceeds requested byte budget')
                while True:
                    chunk=response.read(min(1024*1024,max_bytes-total+1))
                    if not chunk: break
                    total+=len(chunk)
                    if total>max_bytes: raise ValueError('Content exceeds requested byte budget')
                    digest.update(chunk); out.write(chunk)
                    from .review_limits import progress
                    progress(total,int(response.headers.get('Content-Length','0')) or max_bytes,'Fetching selected original into request-only staging')
                mime=response.headers.get_content_type()
            sha=digest.hexdigest()
            if expected_sha256 and sha!=expected_sha256: raise ValueError('Upstream checksum mismatch')
            name=Path(filename or urlsplit(current).path).name or 'asset.bin'
            extension=Path(name).suffix.lower()
            if not extension or len(extension)>10 or not extension[1:].isalnum(): extension='.bin'
            destination=self.root/(sha+extension)
            temp.replace(destination)
            result={'path':str(destination.resolve()),'sha256':sha,'bytes':total,'mime':mime or mimetypes.guess_type(name)[0] or 'application/octet-stream','filename':name}
            info_path.write_text(json.dumps(result),encoding='utf-8')
            return result
        finally:
            if temp.exists(): temp.unlink()

class RangeZip(io.RawIOBase):
    """Seekable remote ZIP transport for central directories and selected members."""
    def __init__(self,cache,url):
        super().__init__()
        self.cache=cache; self.url=url; self.position=0
        _,self.size=cache.range(url,0,1)
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self,offset,whence=0):
        p=offset if whence==0 else self.position+offset if whence==1 else self.size+offset if whence==2 else -1
        if not 0<=p<=self.size: raise ValueError('Invalid archive seek')
        self.position=p; return p
    def read(self,size=-1):
        size=min(self.size-self.position,size if size>=0 else self.size)
        if size==0: return b''
        body,total=self.cache.range(self.url,self.position,size)
        if total!=self.size: raise ValueError('Archive changed while reading')
        self.position+=len(body); return body
