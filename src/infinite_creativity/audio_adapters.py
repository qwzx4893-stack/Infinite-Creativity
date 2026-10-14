"""Per-clip licensed FSD50K originals, accessed inside official multi-part archives."""
import gzip
import hashlib
import json
import zipfile
from pathlib import Path
from .content import ContentCache
from .policy import LICENSES

def fsd50k(c,fetch,run):
    record=fetch.json('https://zenodo.org/api/records/4060432')
    files={f['key']:f for f in record['files']};cache=ContentCache(c.path.parent/'content')
    meta=files['FSD50K.metadata.zip'];received=cache.fetch(meta['links']['self'],meta['key'],16*1024*1024)
    with Path(received['path']).open('rb') as stream:
        if 'md5:'+hashlib.file_digest(stream,'md5').hexdigest()!=meta['checksum']:raise ValueError('FSD50K metadata checksum mismatch')
    with zipfile.ZipFile(received['path']) as archive:
        info_by_split={split:json.loads(archive.read(next(n for n in archive.namelist() if n.endswith(split+'_clips_info_FSD50K.json')))) for split in ('dev','eval')}
    count=0
    for split in ('dev','eval'):
        names=[f'FSD50K.{split}_audio.z{i:02}' for i in range(1,6 if split=='dev' else 2)]+[f'FSD50K.{split}_audio.zip']
        parts=[{'url':files[n]['links']['self'],'bytes':files[n]['size'],'checksum':files[n]['checksum']} for n in names]
        cid=hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()[:24]
        c.db.execute('INSERT OR REPLACE INTO containers VALUES (?,?)',(cid,json.dumps({'type':'split-zip','parts':parts,'license_scope':'Per-clip metadata; dataset license does not override individual recordings.'})))
        inventory=fetch.cache/('fsd-directory-'+cid+'.json.gz')
        if inventory.exists():entries=json.loads(gzip.decompress(inventory.read_bytes()))
        else:
            with cache.multipart_zip(parts) as z:entries=[{'path':i.filename,'bytes':i.file_size,'crc32':i.CRC} for i in z.infolist() if not i.is_dir() and i.filename.endswith('.wav')]
            inventory.write_bytes(gzip.compress(json.dumps(entries).encode()))
        sid='fsd50k:'+split;c.source({'id':sid,'name':'FSD50K / '+split,'url':'https://zenodo.org/records/4060432','adapter':'fsd50k','status':'per-clip-license-metadata','media':['audio'],'attribution':'FSD50K, Fonseca et al.; retain the original uploader credit and recording license.'})
        clips=info_by_split[split]
        for entry in entries:
            key=Path(entry['path']).stem;clip=clips.get(key)
            if not clip:raise ValueError('Archive clip is missing its license metadata: '+key)
            evidence=clip.get('license','').replace('http://','https://',1)
            lic=next((spdx for pattern,spdx in [('publicdomain/zero','CC0-1.0'),('/licenses/by/4.0','CC-BY-4.0'),('/licenses/by/3.0','CC-BY-3.0')] if pattern in evidence),'unknown')
            canonical='https://freesound.org/s/'+key+'/'
            title=clip.get('title',key);author=clip.get('uploader',clip.get('username',clip.get('user','')))
            if not isinstance(author,str):author=str(author)
            tags=[str(t) for t in clip.get('tags',[])]+[str(clip.get('description',''))[:600],'sound-effects','FSD50K']
            if not c.upsert(sid,key,title,'audio',canonical,license=lic,license_url=evidence,author=author,tags=tags,platforms=['game','film','desktop','mobile','web'],formats=['wav'],access_url=parts[-1]['url'],revision=cid,mode='usable' if lic in LICENSES else 'reference',run=run):continue
            aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
            c.set_details(aid,{'description':str(clip.get('description',''))[:2000],'pack_name':'FSD50K / '+split,'pack_scope':split,'files':[{'url':parts[-1]['url'],'container_id':cid,'archive_entry':entry['path'],'filename':Path(entry['path']).name,'relative_path':entry['path'],'bytes':entry['bytes'],'crc32':entry['crc32'],'role':'main'}] if lic in LICENSES else [],'features':{'dataset':'FSD50K','original_recording':key,'original_author':author,'quality_evidence':'Human-labelled sound events; no fabricated aesthetic rating.','rights':'The original per-clip Creative Commons license applies.'}})
            count+=1
        c.reconcile(sid,run);c.db.commit();print(json.dumps({'progress':'fsd50k','split':split,'records':count}),flush=True)
    return count
