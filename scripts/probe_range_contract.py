"""Compare one current original's full and ranged bytes; retain neither."""
import argparse,hashlib,json
from infinite_creativity.live import LiveLibrary,seal


def probe(source,query):
    with LiveLibrary() as library:
        page=library.providers.page(source,{'query':query},'',1)
        if not page['items']:raise ValueError('No current provider candidate')
        asset=page['items'][0];aid=seal('asset',{'source':source,'key':asset['key']})
        with library.content(aid,selected_review=True) as (local,key,current):
            file=next(f for f in local.files(key)['files'] if f.get('role') in {'main','variant'})
            original=local.file(key,file['id'],32*1024*1024)
            body,total=local.cache.range(file['url'],0,min(original['bytes'],1024*1024))
            from pathlib import Path
            expected=Path(original['path']).read_bytes()[:len(body)]
            print(json.dumps({'source':source,'bytes_full':original['bytes'],'range_total':total,'range_bytes':len(body),
                              'full_sha256':original['sha256'],'range_sha256':hashlib.sha256(body).hexdigest(),
                              'prefix_sha256':hashlib.sha256(expected).hexdigest(),'match':body==expected and total==original['bytes'],
                              'original_headers':local.cache.request_headers(file['url'])}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--query',default='landscape');args=parser.parse_args()
    probe(args.source,args.query)
