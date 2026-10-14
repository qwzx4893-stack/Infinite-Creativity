"""Read selected members of official split ZIPs without downloading multi-GB parts."""
import bisect
import io
import struct
import zipfile
import zlib

class SplitRange:
    def __init__(self,cache,parts):
        if not 1<=len(parts)<=64:raise ValueError('Invalid archive part count')
        self.cache=cache;self.parts=parts;self.starts=[0]
        for p in parts:
            if not isinstance(p['bytes'],int) or p['bytes']<=0:raise ValueError('Invalid archive part size')
            self.starts.append(self.starts[-1]+p['bytes'])
        self.size=self.starts[-1]
    def read_at(self,offset,length):
        if offset<0 or length<0 or length>128*1024*1024 or offset+length>self.size:raise ValueError('Invalid split archive range')
        out=[]
        while length:
            disk=bisect.bisect_right(self.starts,offset)-1;p=self.parts[disk]
            n=min(length,self.starts[disk+1]-offset)
            body,total=self.cache.range(p['url'],offset-self.starts[disk],n)
            if total!=p['bytes']:raise ValueError('Archive part changed; refresh metadata')
            out.append(body);length-=len(body);offset+=len(body)
        return b''.join(out)

class MultipartZip:
    def __init__(self,cache,parts):
        self.stream=SplitRange(cache,parts)
        tail_size=min(65557,parts[-1]['bytes']);tail=self.stream.read_at(self.stream.size-tail_size,tail_size)
        offset=tail.rfind(b'PK\x05\x06')
        if offset<0 or len(tail)-offset<22:raise ValueError('Archive has no ZIP end record')
        _,disk,cd_disk,on_disk,total,cd_size,cd_offset,comment=struct.unpack_from('<4s4H2IH',tail,offset)
        if len(tail)-offset!=22+comment:raise ValueError('Invalid ZIP end record')
        if disk!=len(parts)-1 or cd_disk>=len(parts) or total>100000 or cd_size>32*1024*1024:raise ValueError('Unsupported split ZIP layout or oversized directory')
        raw=self.stream.read_at(self.stream.starts[cd_disk]+cd_offset,cd_size)
        self.entries={};pos=0
        while pos<len(raw):
            if pos+46>len(raw):raise ValueError('Truncated ZIP directory')
            fields=struct.unpack_from('<4s6H3I5H2I',raw,pos)
            if fields[0]!=b'PK\x01\x02':raise ValueError('Invalid ZIP directory member')
            flags,method,crc,compressed,size=fields[3],fields[4],fields[7],fields[8],fields[9]
            name_len,extra_len,comment_len,volume=fields[10:14];local=fields[16]
            if volume>=len(parts) or max(compressed,size,local)==0xffffffff:raise ValueError('ZIP64 member requires explicit support; no guessed offsets')
            end=pos+46+name_len+extra_len+comment_len
            if end>len(raw):raise ValueError('Truncated ZIP member metadata')
            name=raw[pos+46:pos+46+name_len].decode('utf-8' if flags&0x800 else 'cp437')
            info=zipfile.ZipInfo(name);info.flag_bits=flags;info.compress_type=method;info.CRC=crc;info.compress_size=compressed;info.file_size=size;info.header_offset=self.stream.starts[volume]+local;info.volume=volume
            if name in self.entries:raise ValueError('Ambiguous duplicate ZIP entry name')
            self.entries[name]=info;pos=end
        if len(self.entries)!=total:raise ValueError('Split ZIP entry count mismatch')
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def infolist(self):return list(self.entries.values())
    def getinfo(self,name):return self.entries[name]
    def read(self,entry,max_bytes=128*1024*1024):
        info=self.getinfo(entry) if isinstance(entry,str) else entry
        if info.flag_bits&1 or info.file_size>max_bytes or info.compress_size>128*1024*1024 or info.file_size>max(1,info.compress_size)*500:raise ValueError('Encrypted or oversized ZIP member')
        header=self.stream.read_at(info.header_offset,30)
        if header[:4]!=b'PK\x03\x04':raise ValueError('Invalid ZIP local header')
        name_len,extra_len=struct.unpack_from('<2H',header,26)
        payload=self.stream.read_at(info.header_offset+30+name_len+extra_len,info.compress_size)
        if info.compress_type==0:body=payload
        elif info.compress_type==8:
            decoder=zlib.decompressobj(-15);body=decoder.decompress(payload,max_bytes+1)
            if len(body)>max_bytes or not decoder.eof:raise ValueError('Oversized or incomplete decompressed ZIP member')
        else:raise ValueError('Unsupported split ZIP compression method')
        if len(body)!=info.file_size or zlib.crc32(body)&0xffffffff!=info.CRC:raise ValueError('ZIP member CRC/size mismatch')
        return body
