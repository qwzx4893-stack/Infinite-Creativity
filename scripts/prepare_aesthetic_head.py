"""Reproduce the tiny MIT software parameters, never unpickle model objects."""
import hashlib,io,json,struct,urllib.request,zipfile
from pathlib import Path

REVISION='6d122adad522ab246644d9dc1c6d7a3810ee255f'
SHA256='c7b14cead230694acc7b9447974d3cad78003c72da032e402a303b6c2429e85f'
ROOT='https://raw.githubusercontent.com/LAION-AI/aesthetic-predictor/'+REVISION+'/'

def prepare():
    body=urllib.request.urlopen(ROOT+'sa_0_4_vit_b_32_linear.pth',timeout=15).read(4097)
    if len(body)!=3047 or hashlib.sha256(body).hexdigest()!=SHA256:raise ValueError('Pinned aesthetic software integrity mismatch')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if set(archive.namelist())!={'archive/data.pkl','archive/data/0','archive/data/1','archive/version'}:raise ValueError('Unexpected pinned software structure')
        weights=struct.unpack('<512f',archive.read('archive/data/0'));bias=struct.unpack('<f',archive.read('archive/data/1'))[0]
    # data.pkl is deliberately never loaded, interpreted or executed.
    notice=urllib.request.urlopen(ROOT+'LICENSE',timeout=15).read(8193)
    if len(notice)>8192 or b'MIT License' not in notice or b'Copyright (c) 2022 LAION AI' not in notice:raise ValueError('Pinned software notice is unavailable')
    target=Path(__file__).resolve().parents[1]/'src/infinite_creativity/data'
    data={'source':'LAION-AI/aesthetic-predictor','source_revision':REVISION,'source_sha256':SHA256,'license':'MIT',
          'format':'Linear 512-dimensional normalized OpenAI CLIP ViT-B/32 image embedding -> scalar aesthetic estimate',
          'weights':weights,'bias':bias}
    (target/'aesthetic_vitb32.json').write_text(json.dumps(data,separators=(',',':'))+'\n',encoding='utf-8')
    (target/'LAION_AESTHETIC_LICENSE.txt').write_bytes(notice)
    print('Prepared 512 pinned software coefficients and MIT notice; no asset/model corpus downloaded.')

if __name__=='__main__':prepare()
