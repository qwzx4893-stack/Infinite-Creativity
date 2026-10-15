import base64,copy,hashlib,io,json,struct,tempfile,unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from infinite_creativity.live_media_review import original_bytes,review_geometry,RequestScreener
from infinite_creativity.meshopt_review import decode_glb
from infinite_creativity.specialized_media import review_path
from infinite_creativity.live import seal,LiveLibrary
from infinite_creativity.live_providers import item
from infinite_creativity.review_board import board

class Classifier:
    def image(self,path):return {'state':'preview-screened','risk_probability':0}

def glb(document,binary):
    text=json.dumps(document).encode();text+=b' '*(-len(text)%4);binary+=b'\0'*(-len(binary)%4)
    return struct.pack('<4sII',b'glTF',2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary

class CollectionMediaTests(unittest.TestCase):
    def test_only_exact_review_images_share_predictions_inside_one_geometry_call(self):
        from unittest.mock import Mock
        classifier=Mock();classifier.image.return_value={'state':'preview-screened'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'view.png';path.write_bytes(b'first');local=RequestScreener(classifier)
            local.image(path);local.image(path);self.assertEqual(classifier.image.call_count,1)
            path.write_bytes(b'changed');local.image(path);self.assertEqual(classifier.image.call_count,2)
            RequestScreener(classifier).image(path);self.assertEqual(classifier.image.call_count,3)
    def compressed(self):
        import meshoptimizer as m
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32);indices=np.array([0,1,2],dtype=np.uint32)
        index=m.encode_index_buffer(indices);binary=index+b'\0'*(-len(index)%4);offset=len(binary);binary+=m.encode_vertex_buffer(vertices)
        document={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)},{'byteLength':44}],'bufferViews':[
            {'buffer':1,'byteOffset':0,'byteLength':6,'extensions':{'EXT_meshopt_compression':{'buffer':0,'byteOffset':0,'byteLength':len(index),'count':3,'byteStride':2,'mode':'TRIANGLES'}}},
            {'buffer':1,'byteOffset':8,'byteLength':36,'extensions':{'EXT_meshopt_compression':{'buffer':0,'byteOffset':offset,'byteLength':len(binary)-offset,'count':3,'byteStride':12,'mode':'ATTRIBUTES'}}}],
            'accessors':[{'bufferView':0,'componentType':5123,'count':3,'type':'SCALAR'},{'bufferView':1,'componentType':5126,'count':3,'type':'VEC3','min':[0,0,0],'max':[1,1,0]}],
            'meshes':[{'primitives':[{'indices':0,'attributes':{'POSITION':1}}]}],'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0,'extensionsRequired':['EXT_meshopt_compression']}
        return document,binary
    def test_meshopt_vertex_and_packed_16bit_index_decode_preserves_geometry(self):
        doc,data=self.compressed();original=glb(doc,data);decoded=decode_glb(original)
        length=struct.unpack_from('<I',decoded,12)[0];result=json.loads(decoded[20:20+length]);start=28+length
        self.assertEqual(struct.unpack_from('<3H',decoded,start+result['bufferViews'][0]['byteOffset']),(0,1,2))
        self.assertEqual(struct.unpack_from('<9f',decoded,start+result['bufferViews'][1]['byteOffset']),(0,0,0,1,0,0,0,1,0))
        self.assertEqual(decode_glb(decoded),decoded)
        with tempfile.TemporaryDirectory() as directory:self.assertEqual(review_geometry(original,Classifier(),directory)['triangles'],1)
    def test_compressed_expansion_and_source_extent_are_bounded_before_decode(self):
        for field,value in [('count',100000000),('byteOffset',999999999),('mode','EXECUTE')]:
            doc,data=self.compressed();doc['bufferViews'][0]['extensions']['EXT_meshopt_compression'][field]=value
            with self.assertRaises(ValueError):decode_glb(glb(doc,data))
    def test_git_lfs_review_verifies_pointer_and_exact_original_without_mutating_manifest(self):
        body=b'current original';digest=hashlib.sha256(body).hexdigest();pointer=('version https://git-lfs.github.com/spec/v1\noid sha256:'+digest+'\nsize '+str(len(body))+'\n').encode()
        original={'url':'https://raw.githubusercontent.com/owner/repo/rev/art.png','sha':hashlib.sha1(('blob '+str(len(pointer))+'\0').encode()+pointer).hexdigest(),'bytes':len(pointer)};before=copy.deepcopy(original)
        class HTTP:
            def read(self,url,*args):return pointer if 'raw.githubusercontent.com' in url else body
        self.assertEqual(original_bytes(HTTP(),{},original),body);self.assertEqual(original,before)
        original['sha']='0'*40
        with self.assertRaisesRegex(ValueError,'integrity'):original_bytes(HTTP(),{},original)
    def test_external_glb_embedded_buffer_and_explicit_relative_texture_are_reviewed(self):
        import trimesh
        pixels=Image.new('RGB',(4,4),'green');mesh=trimesh.creation.box()
        mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),image=pixels)
        body=mesh.export(file_type='glb');length=struct.unpack_from('<I',body,12)[0];doc=json.loads(body[20:20+length]);binary=body[28+length:]
        doc['images']=[{'uri':'Textures/colormap.png'}]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.glb';path.write_bytes(glb(doc,binary));folder=Path(directory)/'Textures';folder.mkdir();pixels.save(folder/'colormap.png')
            result=review_path(path,'glb',Classifier(),directory)
            self.assertEqual(result['triangles'],12);self.assertIn('original GLB plus',result['scope']);self.assertTrue(Path(result['_converted_glb']).is_file())
            (folder/'colormap.png').unlink()
            with self.assertRaisesRegex(ValueError,'dependency'):review_path(path,'glb',Classifier(),directory)
    def test_lfs_preview_uses_the_same_resolved_original_in_request_only_manifest(self):
        url='https://raw.githubusercontent.com/owner/repo/rev/art.png';body=b'image';pointer=('version https://git-lfs.github.com/spec/v1\noid sha256:'+hashlib.sha256(body).hexdigest()+'\nsize '+str(len(body))+'\n').encode()
        original={'url':url,'filename':'art.png','role':'main','bytes':len(pointer),'sha':hashlib.sha1(('blob '+str(len(pointer))+'\0').encode()+pointer).hexdigest()}
        a=item('fixture','art','Forest','illustration','CC0-1.0','https://creativecommons.org/publicdomain/zero/1.0/',formats=['png'],files=[original],previews=[{'url':url}],revision='r1')
        class HTTP:
            def read(self,*args):return pointer
        library=LiveLibrary(HTTP(),{'fixture':{'id':'fixture','adapter':'github-assets','url':'https://example.org','name':'Fixture'}});library.providers.get=lambda *args:copy.deepcopy(a)
        with library.content(seal('asset',{'source':'fixture','key':'art'}),selected_review=True) as (local,key,current):
            self.assertIn('media.githubusercontent.com/media/',current['files'][0]['url']);self.assertEqual(current['previews'][0]['url'],current['files'][0]['url'])
        self.assertEqual(a['previews'][0]['url'],url)
    def test_native_comparison_board_keeps_reference_rights_and_item_failures_separate(self):
        aid=seal('asset',{'source':'fixture','key':'reference'});missing=seal('asset',{'source':'fixture','key':'removed'});paths=[]
        class Library:
            @contextmanager
            def content(self,locator,**kwargs):
                if locator==missing:raise ValueError('Current source removed this item')
                with tempfile.TemporaryDirectory() as directory:
                    path=Path(directory)/'preview.png';Image.new('RGB',(10,10),'green').save(path);paths.append(path)
                    class Local:
                        def preview(self,key):return {'path':str(path)}
                    yield Local(),'local',{}
            def card(self,a):return {'title':'Study only','kind':'visual-reference','source':'fixture','section_id':'inspiration/web','license':'unknown','license_url':'https://example.org/terms','access':'reference'}
        with patch('infinite_creativity.review_board.check_delivery'),patch('infinite_creativity.live_admission.screener',return_value=Classifier()):
            result,pixels=board(Library(),[aid,missing])
        self.assertEqual(len(result['items']),1);self.assertEqual(len(result['unavailable']),1);self.assertNotIn('asset_files',result['items'][0]['actions'])
        with Image.open(io.BytesIO(base64.b64decode(pixels))) as image:self.assertEqual(image.size,(384,280))
        self.assertFalse(any(p.exists() for p in paths))

if __name__=='__main__':unittest.main()
