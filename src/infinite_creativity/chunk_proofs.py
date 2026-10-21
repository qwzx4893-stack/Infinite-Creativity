"""Client-carried exact chunk digests from a complete selected-file review."""
import hashlib
import hmac
import math
from pathlib import Path
from .request_scope import checkpoint

class RangeRepresentationChanged(ValueError):
    """Ranged bytes are unusable; a full signed digest may still verify."""


def attach(staged, receipts):
    total=sum(result['bytes'] for _,_,result in staged.values())
    block=1024*1024
    # Bound total signed digest metadata, even for a 512 MiB selected bundle.
    while math.ceil(total/block)+len(staged)>176:
        block*=2
    for path,file,result in staged.values():
        hashes=[]
        with Path(path).open('rb') as stream:
            while True:
                checkpoint()
                body=stream.read(block)
                if not body:break
                hashes.append(hashlib.sha256(body).hexdigest())
        receipt=receipts[file['_review_key']]
        receipt.update(chunk_bytes=block,chunks=hashes)


def read(cache,file,receipt,offset,length):
    """None means this format has no exact original HTTP range contract."""
    if any(file.get(k) for k in ('archive_entry','container_id','tar_entry','json_content_path','transport_encoding')):
        return None
    hashes=receipt.get('chunks');block=receipt.get('chunk_bytes');total=receipt['bytes']
    if not hashes or not isinstance(block,int) or block<1024*1024:return None
    if offset>total:raise ValueError('Original byte offset exceeds reviewed file size')
    if offset==total:return b''
    if len(hashes)!=math.ceil(total/block):raise ValueError('Invalid signed original chunk scope')
    start=offset//block;end=(min(total,offset+length)-1)//block
    bodies=[]
    for number in range(start,end+1):
        checkpoint()
        body,extent=cache.range(file['url'],number*block,min(block,total-number*block))
        if extent!=total or not hmac.compare_digest(hashlib.sha256(body).hexdigest(),hashes[number]):
            raise RangeRepresentationChanged('Original chunk changed since complete selected review; complete-file revalidation required')
        bodies.append(body)
    return b''.join(bodies)[offset-start*block:offset-start*block+length]
