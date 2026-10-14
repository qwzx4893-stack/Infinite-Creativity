"""Install pinned software once, without a second full model cache."""
import hashlib,os,tempfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request,urlopen
def install(repo,revision,remote,target,digest,max_bytes=512*1024*1024):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:return
    url='https://huggingface.co/'+quote(repo,safe='/')+'/resolve/'+quote(revision,safe='')+'/'+quote(remote,safe='/')+'?download=true'
    descriptor,temp=tempfile.mkstemp(prefix='.model-install-',suffix='.part',dir=target.parent)
    try:
        total=0;checksum=hashlib.sha256()
        with os.fdopen(descriptor,'wb') as output,urlopen(Request(url,headers={'User-Agent':'InfiniteCreativity/0.7'}),timeout=30) as response:
            while True:
                block=response.read(1024*1024)
                if not block:break
                total+=len(block)
                if total>max_bytes:raise ValueError('Pinned model exceeds software download budget')
                checksum.update(block);output.write(block)
        if checksum.hexdigest()!=digest:raise ValueError('Pinned model checksum mismatch')
        Path(temp).replace(target)
    finally:
        if Path(temp).exists():Path(temp).unlink()
