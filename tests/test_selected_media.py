import copy,hashlib,io,json,os,struct,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from infinite_creativity.live import LiveLibrary,seal,unseal,metadata_fingerprint
from infinite_creativity.live_providers import item
from infinite_creativity.content import ContentCache
from infinite_creativity.live_media_review import check_delivery,review_frames
from infinite_creativity.selected_review import review,open_archive,member_path
from infinite_creativity.specialized_media import review_path
from infinite_creativity.review_limits import profile
from infinite_creativity.gltf_review import poses

class Classifier:
    def image(self,path):return {'state':'preview-screened','risk_probability':0}

class SelectedMediaTests(unittest.TestCase):
    def library(self,asset,bodies):
        class HTTP:
            def read(self,url,*args):return bodies[url]
        l=LiveLibrary(HTTP(),{'fixture':{'id':'fixture','adapter':'github-assets','url':'https://example.org','name':'Fixture'}})
        l.providers.get=lambda *args:copy.deepcopy(asset)
        return l
    def fixture(self,body=None):
        if body is None:
            stream=io.BytesIO();Image.new('RGB',(16,16),'green').save(stream,format='PNG');body=stream.getvalue()
        file={'url':'https://example.org/art.png','filename':'art.png','role':'main','relative_path':'art.png','bytes':len(body)}
        return item('fixture','art','Forest art','illustration','CC0-1.0','https://creativecommons.org/publicdomain/zero/1.0/','Artist',formats=['png'],files=[file],revision='r1'),{file['url']:body}
    def cache(self,bodies):
        def fetch(cache,url,filename='',max_bytes=128*1024*1024,*args,**kwargs):
            body=bodies[url]
            if len(body)>max_bytes:raise ValueError('Content exceeds requested byte budget')
            return cache.store(body,filename)
        return patch.object(ContentCache,'fetch',fetch)
    def test_selected_large_file_receipt_delivers_only_exact_bytes_and_fresh_rights(self):
        a,bodies=self.fixture();bodies[a['files'][0]['url']]+=b'\0'*(33*1024*1024);a['files'][0]['bytes']=len(next(iter(bodies.values())))
        body=next(iter(bodies.values()));a['files'][0]['sha']=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest();a['repo']='public/test'
        l=self.library(a,bodies);aid=seal('asset',{'source':'fixture','key':'art'})
        with self.cache(bodies),patch('infinite_creativity.live_admission.screener',return_value=Classifier()),patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            result=review(l,aid);approved=result['asset_id'];self.assertGreater(result['reviewed_bytes'],32*1024*1024)
            with l.content(approved) as (lib,local,current):
                record=lib.file(local,result['selected_file_id'],64*1024*1024);self.assertEqual(record['sha256'],hashlib.sha256(next(iter(bodies.values()))).hexdigest())
                temporary=Path(record['path'])
            self.assertFalse(temporary.exists())
            bodies[a['files'][0]['url']]=b'changed bytes'
            with l.content(approved) as (lib,local,current),self.assertRaisesRegex(ValueError,'differs from indexed revision|changed since selected review'):
                lib.file(local,result['selected_file_id'],64*1024*1024)
            a['license']='unknown'
            with self.assertRaisesRegex(ValueError,'rights, revision'):l.get(approved)
    def test_receipt_is_signed_and_does_not_authorize_unreviewed_variant(self):
        a,bodies=self.fixture();a['files'].append({**a['files'][0],'url':'https://example.org/other.png','filename':'other.png','relative_path':'other.png','role':'variant'})
        l=self.library(a,bodies);aid=seal('asset',{'source':'fixture','key':'art'})
        with self.cache(bodies),patch('infinite_creativity.live_admission.screener',return_value=Classifier()):
            result=review(l,aid);data=unseal(result['asset_id'],'asset');self.assertEqual(len(data['review']['files']),1)
            self.assertEqual(len(l.get(result['asset_id'])['files']),1)
            with self.assertRaises(ValueError):l.get(result['asset_id'][:-4]+'AAAA')
    def test_gltf_missing_or_external_dependencies_are_never_resolved_by_renderer(self):
        for uri in ('../unscoped.bin','https://example.org/buffer.bin','file:///private.bin'):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'scene.gltf';path.write_text(json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':uri,'byteLength':12}]}))
                with self.assertRaisesRegex(ValueError,'GLTF'):review_path(path,'gltf',Classifier(),directory)
    def test_pending_native_metadata_is_separate_from_admitted_assets(self):
        a,bodies=self.fixture();a.update(kind='model-3d',formats=['fbx'],previews=[]);a['files'][0].update(filename='scene.fbx',relative_path='scene.fbx')
        l=self.library(a,bodies);l.providers.page=lambda *args:{'items':[copy.deepcopy(a)],'next':None}
        with patch('infinite_creativity.live_admission.screener',return_value=Classifier()),patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            result=l.open(source='fixture',limit=1)
            self.assertEqual(result['items'],[]);self.assertEqual(len(result['review_queue']),1)
            self.assertEqual(result['review_queue'][0]['access'],'pending-original-review')
            self.assertNotIn('read_asset_file',result['review_queue'][0]['actions'])
            a['title']='sexual scene';self.assertEqual(l.open(source='fixture',limit=1)['review_queue'],[])
    def test_archive_member_locator_reloads_inventory_and_binds_current_crc(self):
        a,bodies=self.fixture();stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('art.png',next(iter(bodies.values())));z.writestr('../unscoped.png',b'bad')
        body=stream.getvalue();a.update(kind='asset-pack',formats=['zip']);a['files']=[{'url':'https://example.org/pack.zip','filename':'pack.zip','relative_path':'pack.zip','bytes':len(body),'role':'main'}];bodies={a['files'][0]['url']:body}
        l=self.library(a,bodies);aid=seal('asset',{'source':'fixture','key':'art'})
        with patch.object(ContentCache,'remote_zip',lambda cache,url:zipfile.ZipFile(io.BytesIO(bodies[url]))),self.cache(bodies),patch('infinite_creativity.live_admission.screener',return_value=Classifier()):
            listed=open_archive(l,aid);self.assertEqual([v['entry'] for v in listed['members']],['art.png'])
            chosen=open_archive(l,aid,entry='art.png');result=review(l,chosen['asset_id']);self.assertEqual(l.get(result['asset_id'])['files'][0]['archive_entry'],'art.png')
            changed=io.BytesIO()
            with zipfile.ZipFile(changed,'w') as z:z.writestr('art.png',b'changed')
            bodies[a['files'][0]['url']]=changed.getvalue()
            with self.assertRaisesRegex(ValueError,'rights, revision'):l.get(result['asset_id'])
    def test_hidden_psd_layer_is_screened(self):
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        class BadFinal:
            def image(self,path):
                with Image.open(path) as image:r,g,b=image.convert('RGB').getpixel((0,0));bad=r>200 and g<100
                return {'state':'review-required' if bad else 'preview-screened','risk_probability':1 if bad else 0}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'art.psd';doc=PSDImage.new('RGBA',(16,16),color=(0,200,0,255));layer=PixelLayer.frompil(Image.new('RGBA',(16,16),(255,0,0,255)),doc,'Hidden layer');layer.visible=False;doc.save(path)
            with self.assertRaisesRegex(ValueError,'sexual/suggestive'):review_path(path,'psd',BadFinal(),directory)
    def test_all_ora_layers_are_reviewed_and_unsafe_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'art.ora';stream=io.BytesIO();Image.new('RGB',(16,16),'green').save(stream,format='PNG')
            with zipfile.ZipFile(path,'w') as z:z.writestr('mergedimage.png',stream.getvalue());z.writestr('data/hidden.png',stream.getvalue())
            result=review_path(path,'ora',Classifier(),directory);self.assertEqual(result['layers'],2)
        for name in ('../private.png','C:/file.png','/file.png','x\\y.png'):
            with self.assertRaises(ValueError):member_path(name)
    def test_extended_review_reads_all_300_animation_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sequence.gif';images=[Image.new('RGB',(2,2),(i%256,(i//256)*200,10)) for i in range(300)];images[0].save(path,save_all=True,append_images=images[1:],duration=20)
            with self.assertRaisesRegex(ValueError,'full-frame'):review_frames(path,'gif',Classifier(),directory)
            with profile('extended'):self.assertEqual(review_frames(path,'gif',Classifier(),directory)['frames'],300)
    def test_cubic_interpolation_and_sparse_morph_positions(self):
        binary=bytearray();views=[];accessors=[]
        def data(body,component,count,kind):
            while len(binary)%4:binary.append(0)
            index=len(views);views.append({'buffer':0,'byteOffset':len(binary),'byteLength':len(body)});binary.extend(body)
            accessors.append({'bufferView':index,'componentType':component,'count':count,'type':kind});return len(accessors)-1
        positions=data(struct.pack('<9f',0,0,0,1,0,0,0,1,0),5126,3,'VEC3');indices=data(struct.pack('<3H',0,1,2),5123,3,'SCALAR');times=data(struct.pack('<2f',0,1),5126,2,'SCALAR')
        values=data(struct.pack('<6f',0,0,0,0,1,0),5126,6,'SCALAR')
        sparse_index=data(b'\0',5121,1,'SCALAR');sparse_value=data(struct.pack('<3f',2,0,0),5126,1,'VEC3')
        accessors.append({'componentType':5126,'count':3,'type':'VEC3','sparse':{'count':1,'indices':{'bufferView':accessors[sparse_index]['bufferView'],'componentType':5121},'values':{'bufferView':accessors[sparse_value]['bufferView']}}});target=len(accessors)-1
        doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors,'nodes':[{'mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':positions},'indices':indices,'targets':[{'POSITION':target}]}]}],'animations':[{'samplers':[{'input':times,'output':values,'interpolation':'CUBICSPLINE'}],'channels':[{'sampler':0,'target':{'node':0,'path':'weights'}}]}]}
        document=json.dumps(doc).encode();document+=b' '*(-len(document)%4);binary+=b'\0'*(-len(binary)%4)
        body=struct.pack('<4sII',b'glTF',2,28+len(document)+len(binary))+struct.pack('<II',len(document),0x4e4f534a)+document+struct.pack('<II',len(binary),0x004e4942)+binary
        result=list(poses(body));self.assertEqual(len(result),3);self.assertAlmostEqual(result[1][0][0][0],1);self.assertAlmostEqual(result[2][0][0][0],2)
    def test_kenney_ignores_unrelated_navigation_links_before_applying_page_quota(self):
        from infinite_creativity.live_packs import kenney
        calls=[]
        class HTTP:
            def text(self,url):
                calls.append(url)
                if 'search=' in url:return ''.join('<a href="https://kenney.nl/assets/'+name+'">Pack</a>' for name in ('building-kit','brick-kit','car-kit','toy-car-kit'))
                return '<h1>'+('Car Kit' if url.endswith('/car-kit') else 'Toy Car Kit' if url.endswith('/toy-car-kit') else 'Building Kit')+'</h1>CC0'
        result=kenney(HTTP(),{'id':'kenney'},{'query':'car kit'},'',1)
        self.assertEqual(result['items'][0]['key'],'car-kit');self.assertIn('search=car%20kit',calls[0]);self.assertIsNotNone(result['next'])
    def test_khronos_continues_scanned_windows_when_query_matches_are_sparse(self):
        from infinite_creativity.live_media import khronos
        entries=[{'path':f'Models/Model{i:02d}/metadata.json','type':'blob','sha':'a','size':100} for i in range(18)]+[{'path':f'Models/Model{i:02d}/glTF/model.gltf','type':'blob','sha':'a','size':100} for i in range(18)]
        class HTTP:
            def json(self,url):
                if url.endswith('glTF-Sample-Assets'):return {'default_branch':'main'}
                if '/commits/' in url:return {'sha':'c'}
                if '/git/trees/' in url:return {'tree':entries,'truncated':False}
                return {'name':'Target cube' if 'Model17' in url else 'Other cube','legal':[{'spdx':'CC0-1.0','artist':'Artist'}]}
        first=khronos(HTTP(),{'id':'khronos'},{'query':'target'},'',1);self.assertEqual(first['items'],[]);self.assertEqual(first['next'],'Models/Model15')
        last=khronos(HTTP(),{'id':'khronos'},{'query':'target'},first['next'],1);self.assertEqual(last['items'][0]['key'],'Models/Model17');self.assertIsNone(last['next'])
    def test_unused_embedded_glb_texture_is_still_screened(self):
        import trimesh
        from infinite_creativity.live_media_review import review_geometry
        source=trimesh.creation.box().export(file_type='glb');length=struct.unpack_from('<I',source,12)[0];doc=json.loads(source[20:20+length]);offset=28+length;binary=bytearray(source[offset:])
        stream=io.BytesIO();Image.new('RGB',(16,16),'red').save(stream,format='PNG');pixels=stream.getvalue()
        while len(binary)%4:binary.append(0)
        doc['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(pixels)});binary.extend(pixels);doc['buffers'][0]['byteLength']=len(binary);doc['images']=[{'bufferView':len(doc['bufferViews'])-1,'mimeType':'image/png'}]
        document=json.dumps(doc).encode();document+=b' '*(-len(document)%4);binary+=b'\0'*(-len(binary)%4)
        body=struct.pack('<4sII',b'glTF',2,28+len(document)+len(binary))+struct.pack('<II',len(document),0x4e4f534a)+document+struct.pack('<II',len(binary),0x004e4942)+binary
        class Reject:
            def image(self,path):return {'state':'review-required','risk_probability':1}
        with tempfile.TemporaryDirectory() as directory,self.assertRaisesRegex(ValueError,'sexual/suggestive'):review_geometry(body,Reject(),directory)

if __name__=='__main__':unittest.main()
