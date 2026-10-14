import base64
import hashlib
import io
import json
import os
import struct
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch,Mock
from email.message import Message
from infinite_creativity.catalog import Catalog
from infinite_creativity.content import ContentCache,RangeZip,validate_url
from infinite_creativity.library import Library
from infinite_creativity.runtime import Runtime
from infinite_creativity.service import resolve
from infinite_creativity.kenney import index_pack,inventory
from infinite_creativity.asset_adapters import github_assets,khronos

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=Catalog(Path(self.tmp.name)/'catalog.sqlite')
        self.l=Library(self.c)
    def tearDown(self): self.l.close(); self.c.close(); self.tmp.cleanup()
    def asset(self,title='chair',kind='model-3d',mode='usable',files=None):
        url='https://github.com/fixture/pack#'+title
        self.c.upsert('fixture',title,title,kind,url,license='CC0-1.0',license_url='https://github.com/fixture/pack/LICENSE',mode=mode,formats=['glb'],platforms=['desktop'],tags=['low-poly'],revision='r1')
        aid=hashlib.sha256(url.encode()).hexdigest()[:24]
        if files is not None: self.c.set_details(aid,{'files':files})
        self.c.db.commit(); return aid
    def cached(self,url,filename,body):
        r=self.l.cache.store(body,filename)
        (self.l.cache.root/(hashlib.sha256(url.encode()).hexdigest()+'.receipt.json')).write_text(json.dumps(r))
        return r
    def test_ranked_seek_and_signed_session_traverse_entire_inventory(self):
        for i in range(81): self.asset('chair '+str(i))
        view=self.l.open(query='chair',kind='model-3d',format='glb'); ids=[]
        while True:
            ids.extend(a['id'] for a in view['items'])
            self.assertTrue(all(a['resource_uri'].startswith('creativity://asset/') and 'canonical_url' not in a for a in view['items']))
            if not view['next_cursor']: break
            view=self.l.page(view['session_id'],view['next_cursor'],limit=17)
        self.assertEqual(len(set(ids)),81)
        self.assertEqual(self.c.facets('model-3d')['formats']['glb'],81)
        other=self.l.open(kind='model-3d')
        token=other['next_cursor']
        with self.assertRaises(ValueError): self.l.runtime.position('wrong-session',token)
        with self.assertRaises(ValueError): self.l.runtime.position(other['session_id'],token+'x')
        self.c.db.execute("INSERT INTO sync_runs(source,status) VALUES ('refresh','running')"); self.c.db.commit()
        with self.assertRaisesRegex(ValueError,'refreshed'): self.l.page(other['session_id'],token)
    def test_reference_never_fetches_content(self):
        aid=self.asset(mode='reference')
        with patch.object(self.l.cache,'fetch') as fetch:
            with self.assertRaises(ValueError): self.l.file(aid)
            with self.assertRaises(ValueError): self.l.preview(aid)
            fetch.assert_not_called()
    def test_compressed_transport_checks_original_blob_then_expands_bounded_text(self):
        import gzip
        text=b'LUT_3D_SIZE 2\n'+b'0 0 0\n'*8;body=gzip.compress(text);url='https://raw.githubusercontent.com/fixture/pack/pinned/look.cube.gz'
        self.cached(url,'look.cube',body);sha=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
        aid=self.asset(kind='lut',files=[{'url':url,'filename':'look.cube','sha':sha,'transport':'gzip','role':'main'}])
        self.assertEqual(self.l.code(aid)['text'],text.decode().rstrip())
        self.assertEqual(self.l.inspect_media(aid)['lut']['numeric_rows'],8)
    def test_private_sessions_expire_and_collections_are_outside_export(self):
        aid=self.asset(); view=self.l.open()
        cid=self.l.runtime.collection('private project'); self.l.runtime.add(cid,[aid,aid])
        self.assertEqual(self.l.runtime.items(cid),[aid])
        self.assertFalse(self.c.db.execute("SELECT 1 FROM sqlite_master WHERE name='collections'").fetchone())
        self.l.runtime.db.execute('UPDATE sessions SET created=?',(time.time()-86401,)); self.l.runtime.db.commit()
        with self.assertRaises(ValueError): self.l.page(view['session_id'])
    def test_original_text_chunk_and_bundle_preserve_paths_and_budget(self):
        root='https://raw.githubusercontent.com/fixture/pack/pinned/'
        body=b'import { colors } from "./colors";\nexport const chair = colors;\n'
        self.cached(root+'chair.ts','chair.ts',body); self.cached(root+'colors.ts','colors.ts',b'export const colors = "green";')
        aid=self.asset(files=[{'url':root+'chair.ts','filename':'chair.ts','relative_path':'src/chair.ts','role':'main'},{'url':root+'colors.ts','filename':'colors.ts','relative_path':'src/colors.ts','role':'dependency'},{'url':root+'alternative.ts','filename':'alternative.ts','role':'variant'}])
        code=self.l.code(aid,line_count=1)
        self.assertIn('./colors',code['dependencies']); self.assertEqual(code['text'],body.decode().splitlines()[0])
        fid=self.l.files(aid)['files'][0]['id']
        chunk=self.l.chunk(aid,fid,offset=7,length=12)
        self.assertEqual(base64.b64decode(chunk['data']),body[7:19])
        bundle=self.l.bundle(aid,max_total_bytes=1000)
        self.assertEqual([f['relative_path'] for f in bundle['files']],['src/chair.ts','src/colors.ts'])
        with self.assertRaises(ValueError): self.l.bundle(aid,max_total_bytes=10)
        with self.assertRaises(ValueError): self.l.file(aid,'bad-file')
    def test_pinned_blob_hash_and_conflicting_license(self):
        body=b'// SPDX-License-Identifier: MIT\nexport const button = 1;'
        sha=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
        aid=self.asset(kind='ui-component',files=[{'url':'https://raw.githubusercontent.com/a/b/main/button.ts','filename':'button.ts','sha':sha}])
        self.c.source({'id':'fixture','repo':'a/b','adapter':'github-tree'}); self.c.db.commit()
        with patch.object(self.l.fetch,'json',return_value={'content':base64.b64encode(body).decode(),'size':len(body)}):
            with self.assertRaisesRegex(ValueError,'license declaration'): self.l.file(aid)
        with patch.object(self.l.fetch,'json',return_value={'content':base64.b64encode(b'changed').decode(),'size':7}):
            with self.assertRaisesRegex(ValueError,'indexed revision'): self.l.file(aid)
    def test_glb_reports_actual_rigs_clips_triangles(self):
        doc={'asset':{'version':'2.0'},'meshes':[{'primitives':[{'indices':0}]}],'accessors':[{'count':12}],'skins':[{}],'animations':[{'name':'Walk'},{'name':'Idle'}],'materials':[{}],'nodes':[{}],'buffers':[{'uri':'body.bin'}]}
        payload=json.dumps(doc).encode(); payload+=b' '*((-len(payload))%4)
        body=struct.pack('<4sIIII',b'glTF',2,20+len(payload),len(payload),0x4E4F534A)+payload
        url='https://raw.githubusercontent.com/a/b/pinned/rig.glb'; self.cached(url,'rig.glb',body)
        aid=self.asset(files=[{'url':url,'filename':'rig.glb'}]); result=self.l.inspect_3d(aid)
        self.assertEqual(result['skins'],1); self.assertEqual(result['animation_clips'],['Walk','Idle'])
        self.assertEqual(result['indexed_triangles'],4); self.assertEqual(result['external_dependencies'],['body.bin'])
    def test_archive_crc_member_budgets_and_unsafe_paths(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('textures/wood.txt','wood texture'); z.writestr('../escape.txt','bad'); z.writestr('bomb.txt',b'0'*1024*1024)
        archive=buf.getvalue(); calls=[]
        def ranged(url,start,length): calls.append((start,length)); return archive[start:start+length],len(archive)
        aid=self.asset(files=[{'url':'https://kenney.nl/media/pack.zip','archive_entry':'textures/wood.txt','filename':'wood.txt','role':'main'}])
        with patch.object(self.l.cache,'range',side_effect=ranged):
            result=self.l.file(aid,max_bytes=20)
            self.assertEqual(Path(result['path']).read_bytes(),b'wood texture')
        self.assertGreater(len(calls),1)
        with patch.object(self.l.cache,'range',side_effect=RuntimeError('offline')):
            self.assertEqual(self.l.file(aid)['sha256'],result['sha256'])
        bad=self.asset('bad',files=[{'url':'https://kenney.nl/media/pack.zip','archive_entry':'../escape.txt','filename':'escape.txt'}])
        with self.assertRaisesRegex(ValueError,'Unsafe'): self.l.file(bad)
        bomb=self.asset('bomb',files=[{'url':'https://kenney.nl/media/pack.zip','archive_entry':'bomb.txt','filename':'bomb.txt'}])
        with patch.object(self.l.cache,'range',side_effect=ranged):
            with self.assertRaisesRegex(ValueError,'safe content budget'): self.l.file(bomb)
    def test_polyhaven_bundle_includes_only_selected_variant_dependencies(self):
        payload={'blend':{'1k':{'blend':{'url':'https://dl.polyhaven.org/main.blend','include':{'textures/a.jpg':{'url':'https://dl.polyhaven.org/a.jpg'}}}},'2k':{'blend':{'url':'https://dl.polyhaven.org/large.blend'}}}}
        aid=self.asset(); self.c.db.execute("UPDATE assets SET source='polyhaven' WHERE id=?",(aid,)); self.c.db.commit()
        with patch('infinite_creativity.service.Fetcher.json',return_value=payload): files=self.l.files(aid)['files']
        self.assertEqual(files[1]['relative_path'],'textures/a.jpg')
        with patch.object(self.l,'file',side_effect=lambda a,f,b:{'file_id':f,'bytes':5}):
            bundle=self.l.bundle(aid)
        self.assertEqual(len(bundle['files']),2)
    def test_font_default_bundle_keeps_license_and_preferred_original(self):
        aid=self.asset(kind='font')
        self.c.db.execute("UPDATE assets SET source='google-fonts',upstream_id='ofl/family/METADATA.pb' WHERE id=?",(aid,)); self.c.db.commit()
        payload=[{'name':name,'download_url':'https://raw.githubusercontent.com/google/fonts/main/ofl/family/'+name,'sha':'a'*40} for name in ('OFL.txt','Regular.ttf','Bold.ttf')]
        with patch('infinite_creativity.service.Fetcher.json',return_value=payload):
            manifest=self.l.files(aid)
        self.assertEqual(manifest['files'][0]['filename'],'Regular.ttf')
        with patch.object(self.l,'file',side_effect=lambda a,f,b:{'file_id':f,'bytes':5}): bundle=self.l.bundle(aid)
        ids={f['file_id'] for f in bundle['files']}
        self.assertEqual({f['filename'] for f in manifest['files'] if f['id'] in ids},{'Regular.ttf','OFL.txt'})
    def test_component_manifest_keeps_original_repository_path(self):
        aid=self.asset(kind='ui-component')
        self.c.source({'id':'fixture','repo':'a/b','adapter':'github-tree'})
        self.c.db.execute("UPDATE assets SET upstream_id='src/ui/button.tsx',revision=?,access_url='https://raw.githubusercontent.com/a/b/main/src/ui/button.tsx' WHERE id=?",('a'*40,aid));self.c.db.commit()
        self.assertEqual(self.l.files(aid)['files'][0]['relative_path'],'src/ui/button.tsx')

class TransportTests(unittest.TestCase):
    def test_urls_cannot_access_private_network_or_credentials(self):
        for url in ['http://kenney.nl/a.zip','https://x:secret@kenney.nl/a.zip','https://kenney.nl:8080/a.zip','https://evilkenney.nl/a.zip','https://localhost/a']:
            with self.assertRaises(ValueError): validate_url(url,False)
        with patch('socket.getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError): validate_url('https://kenney.nl/a.zip')
    def test_range_rejects_ignored_range_instead_of_downloading_archive(self):
        with tempfile.TemporaryDirectory() as td:
            cache=ContentCache(td); response=Mock(); response.status=200; response.headers={'Content-Range':''}
            response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
            with patch('infinite_creativity.content.validate_url'),patch.object(cache.opener,'open',return_value=response):
                with self.assertRaisesRegex(ValueError,'bounded archive ranges'): cache.range('https://kenney.nl/a.zip',0,10)
            response.read.assert_not_called()
    def test_ranged_zip_reads_license_and_member_without_whole_archive(self):
        body=io.BytesIO()
        with zipfile.ZipFile(body,'w') as z:
            z.writestr('License.txt','CC0 1.0 Universal'); z.writestr('wood.obj','original mesh'); z.writestr('large.bin',os.urandom(2*1024*1024))
        archive=body.getvalue(); requested=[]
        with tempfile.TemporaryDirectory() as td:
            cache=ContentCache(td)
            def read(url,start,length): requested.append(length); return archive[start:start+length],len(archive)
            with patch.object(cache,'range',side_effect=read):
                result=inventory(cache,'https://kenney.nl/media/a.zip',Path(td))
            self.assertEqual(len(result['entries']),3); self.assertEqual(result['license_files'],['License.txt'])
            self.assertLess(sum(requested),10000)
    def test_legacy_archive_requires_explicit_creator_page_dedication(self):
        body=io.BytesIO()
        with zipfile.ZipFile(body,'w') as z:
            z.writestr('readme.txt','You may use these graphics in personal and commercial projects.')
            z.writestr('road.png',b'original')
        archive=body.getvalue()
        with tempfile.TemporaryDirectory() as td:
            cache=ContentCache(td)
            with patch.object(cache,'range',side_effect=lambda url,start,length:(archive[start:start+length],len(archive))):
                with self.assertRaisesRegex(ValueError,'explicit CC0'): inventory(cache,'https://kenney.nl/media/legacy.zip',Path(td))
                result=inventory(cache,'https://kenney.nl/media/legacy.zip',Path(td),license_page_cc0=True)
            self.assertEqual(result['license_evidence'],'official-pack-page-cc0')
            self.assertEqual(result['license_files'],[])
    def test_ui_pack_groups_original_vector_and_raster_variants(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('License.txt','CC0 1.0 Universal')
            z.writestr('PNG/button.png',b'original png')
            z.writestr('SVG/button.svg','<svg/>')
            z.writestr('Preview.png',b'package preview')
        archive=buf.getvalue()
        with tempfile.TemporaryDirectory() as td:
            c=Catalog(Path(td)/'catalog.sqlite'); cache=ContentCache(Path(td)/'content')
            text='<a href="https://kenney.nl/assets/category:2D">2D</a><a href="https://kenney.nl/media/pages/assets/ui-pack/fixture.zip">Free download</a>'
            with patch('infinite_creativity.kenney.page',return_value=text),patch('infinite_creativity.kenney.validate_url'),patch.object(cache,'range',side_effect=lambda url,start,length:(archive[start:start+length],len(archive))):
                self.assertEqual(index_pack(c,cache,'https://kenney.nl/assets/ui-pack',Path(td),'run'),1)
            a=c.search(kind='ui-asset')['items'][0]
            self.assertEqual(a['formats'],['png','svg'])
            self.assertEqual(len(c.details(a['id'])['files']),3)
            c.close()
    def test_fetch_stream_budget_cleans_partial_file(self):
        class Response(io.BytesIO):
            def __init__(self):
                super().__init__(b'x'*11); self.headers=Message(); self.headers['Content-Type']='application/octet-stream'
        with tempfile.TemporaryDirectory() as td:
            cache=ContentCache(td)
            with patch('infinite_creativity.content.validate_url'),patch.object(cache.opener,'open',return_value=Response()):
                with self.assertRaisesRegex(ValueError,'byte budget'): cache.fetch('https://kenney.nl/a.zip',max_bytes=10)
            self.assertFalse(list(Path(td).glob('*.part')))
    def test_software_mit_does_not_relicense_repository_media(self):
        with tempfile.TemporaryDirectory() as td:
            c=Catalog(Path(td)/'catalog.sqlite')
            class Fetch:
                def json(self,url):
                    if '/commits/' in url: return {'sha':'a'*40}
                    if '/trees/' in url: return {'tree':[{'type':'blob','path':'chair.glb','sha':'b'*40}]}
                    return {'default_branch':'main','license':{'spdx_id':'MIT'}}
            with self.assertRaisesRegex(RuntimeError,'CC0 license'): github_assets(c,Fetch(),{'repo':'fixture/pack','id':'fixture'},'r1')
            self.assertEqual(c.search()['total'],0); c.close()
    def test_khronos_all_component_licenses_must_allow_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            c=Catalog(Path(td)/'catalog.sqlite')
            class Fetch:
                def json(self,url):
                    if '/commits/' in url: return {'sha':'a'*40}
                    if '/trees/' in url: return {'tree':[{'type':'blob','path':f'Models/{name}/{file}','sha':'b'*40} for name in ('Free','Restricted') for file in ('metadata.json','glTF-Binary/model.glb')]}
                    if url.endswith('metadata.json'):
                        lic='CC-BY-NC-4.0' if '/Restricted/' in url else 'CC0-1.0'
                        return {'legal':[{'spdx':'CC-BY-4.0','artist':'Artist'},{'spdx':lic,'artist':'Other artist'}]}
                    return {'default_branch':'main'}
            self.assertEqual(khronos(c,Fetch(),'run'),2)
            self.assertEqual(c.search(mode='usable')['total'],1)
            self.assertEqual(c.search(mode='reference')['total'],1)
            restricted=c.search(mode='reference')['items'][0]
            self.assertEqual(c.details(restricted['id'])['files'],[]); c.close()

if __name__=='__main__': unittest.main()
