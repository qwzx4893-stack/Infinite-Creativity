"""Bounded, in-memory EXT_meshopt_compression decoding for original review.

Uses the separately installed MIT meshoptimizer binding; no upstream decoder
source or asset is vendored. Original delivery keeps the original compressed
bytes and checksum. Only the temporary inspection representation is expanded.
"""
import json,struct
from .review_limits import limits

def decode_glb(body):
    if len(body)<20 or body[:4]!=b'glTF':raise ValueError('Invalid original GLB')
    version,total,size,kind=struct.unpack_from('<IIII',body,4)
    if version!=2 or total!=len(body) or kind!=0x4E4F534A or size>16*1024*1024 or 20+size>len(body):raise ValueError('Invalid original GLB extent')
    document=json.loads(body[20:20+size]);views=document.get('bufferViews',[])
    if not any('EXT_meshopt_compression' in v.get('extensions',{}) for v in views):return body
    try:import meshoptimizer as decoder
    except ImportError as e:raise ValueError('Meshopt original needs the local meshoptimizer media dependency') from e
    import numpy as np
    if any(b.get('uri') for b in document.get('buffers',[])):raise ValueError('Meshopt external buffers require explicitly scoped conversion')
    offset=20+size;binary=b''
    while offset+8<=len(body):
        length,kind=struct.unpack_from('<II',body,offset);offset+=8
        if offset+length>len(body):raise ValueError('Invalid Meshopt GLB binary extent')
        if kind==0x004E4942:binary=body[offset:offset+length]
        offset+=length
    def number(value):
        if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Invalid Meshopt count/offset')
        return value
    def segment(record):
        start=number(record.get('byteOffset',0));length=number(record['byteLength'])
        if record.get('buffer',0)!=0 or start+length>len(binary):raise ValueError('Meshopt source buffer is missing or exceeds original bounds')
        return binary[start:start+length]
    expanded=bytearray()
    for view in views:
        compressed=view.get('extensions',{}).get('EXT_meshopt_compression')
        if compressed:
            count=number(compressed['count']);stride=number(compressed['byteStride']);size=count*stride
            if not count or count>limits()['triangles']*3 or not 1<=stride<=256 or size!=view['byteLength'] or len(expanded)+size>limits()['bytes']:raise ValueError('Meshopt expanded buffer exceeds review budget or has an invalid stride')
            encoded=segment(compressed);mode=compressed['mode'];filter_name=compressed.get('filter','NONE')
            if mode=='ATTRIBUTES':
                if stride%4:raise ValueError('Invalid Meshopt attribute stride')
                decoded=decoder.decode_vertex_buffer(count,stride,encoded,dtype=np.dtype(('u1',(stride,))))
                filters={'OCTAHEDRAL':(decoder.decode_filter_oct,{4,8}),'QUATERNION':(decoder.decode_filter_quat,{8}),'EXPONENTIAL':(decoder.decode_filter_exp,set(range(4,257,4)))}
                if filter_name!='NONE':
                    if filter_name not in filters or stride not in filters[filter_name][1]:raise ValueError('Unsupported Meshopt filter/stride')
                    decoded=filters[filter_name][0](decoded,count,stride)
            elif mode in {'TRIANGLES','INDICES'} and stride in {2,4} and filter_name=='NONE':
                if mode=='TRIANGLES' and count%3:raise ValueError('Invalid Meshopt triangle count')
                fn=decoder.decode_index_buffer if mode=='TRIANGLES' else decoder.decode_index_sequence
                decoded=fn(count,stride,encoded)
            else:raise ValueError('Unsupported Meshopt mode/filter')
            # The binding allocates uint32 storage even for packed 16-bit
            # indices. Read its written bytes, not a numeric uint16 cast.
            data=decoded.tobytes()[:size]
            if len(data)!=size:raise ValueError('Meshopt decoder returned an invalid byte extent')
            view['extensions'].pop('EXT_meshopt_compression')
        else:data=segment(view)
        if len(expanded)+len(data)>limits()['bytes']:raise ValueError('Expanded Meshopt scene exceeds request byte budget')
        expanded.extend(b'\0'*(-len(expanded)%4));view.update(buffer=0,byteOffset=len(expanded),byteLength=len(data));expanded.extend(data)
    document['buffers']=[{'byteLength':len(expanded)}]
    for field in ('extensionsUsed','extensionsRequired'):
        if field in document:document[field]=[v for v in document[field] if v!='EXT_meshopt_compression']
    header=json.dumps(document,separators=(',',':')).encode();header+=b' '*(-len(header)%4);expanded.extend(b'\0'*(-len(expanded)%4))
    return struct.pack('<4sII',b'glTF',2,28+len(header)+len(expanded))+struct.pack('<II',len(header),0x4E4F534A)+header+struct.pack('<II',len(expanded),0x004E4942)+expanded
