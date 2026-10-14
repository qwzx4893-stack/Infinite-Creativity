import io,json,os,struct,tempfile,unittest,wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from infinite_creativity.live_catalogs import cc_license
from infinite_creativity.live_public_assets import lazytextures,opengameart,internet_archive
from infinite_creativity.live_media_review import review_frames,review_audio,review_geometry,check_delivery
from infinite_creativity.gltf_review import poses

class HTTP:
    def approve_content(self,url):pass

class PublicAssetsTests(unittest.TestCase):
    def test_model_install_failure_keeps_old_software_and_leaves_no_duplicate_cache(self):
        from infinite_creativity.model_download import install
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'model.onnx';target.write_bytes(b'old software')
            with patch('infinite_creativity.model_download.urlopen',return_value=io.BytesIO(b'wrong model')),self.assertRaisesRegex(ValueError,'checksum'):
                install('trusted/model','pinned','model.onnx',target,'0'*64)
            self.assertEqual(target.read_bytes(),b'old software');self.assertEqual([p.name for p in Path(folder).iterdir()],['model.onnx'])
    def test_licence_requires_the_actual_creative_commons_host_and_exact_path(self):
        self.assertEqual(cc_license('https://evil.test/creativecommons.org/licenses/by/4.0/')[0],'unknown')
        self.assertEqual(cc_license('https://creativecommons.org/licenses/by/4.0/fake')[0],'unknown')
        self.assertEqual(cc_license('http://creativecommons.org/licenses/by/4.0/')[0],'CC-BY-4.0')
    def test_art_item_does_not_inherit_the_footer_cc0_or_external_files(self):
        class Fixture(HTTP):
            def text(self,url):return '''<h1>Forest tiles</h1><div class="field field-name-field-art-licenses"><a href="https://creativecommons.org/licenses/by/4.0/">BY</a></div><div class="field field-name-field-art-type">2D Art</div><div class="field field-name-field-art-files"><a href="/sites/default/files/forest.png">File</a></div><footer><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></footer>'''
        a=opengameart(Fixture(),{'id':'oga'},{},'',1,key='forest')
        self.assertEqual(a['license'],'CC-BY-4.0');self.assertEqual(a['title'],'Forest tiles');self.assertEqual(a['files'][0]['filename'],'forest.png')
    def test_lazy_manifest_and_preview_come_from_live_public_infos(self):
        class Fixture(HTTP):
            def json(self,url):
                if url.endswith('Infos.json'):return {'textures':{'1k':[{'name':'Wood.png','path':'/Assets/Wood/1k/Wood.png'}]},'downloads':{'1k':{'name':'Wood.zip','path':'/Assets/Wood/1k/Wood.zip'}}}
                return {'data':[{'name':'Wood','basePath':'/Assets/Wood','preview':{'name':'Preview.png'},'infosFile':{'path':'/Assets/Wood/Infos.json'},'tags':['wood']}]}
        a=lazytextures(Fixture(),{'id':'lazy','media':'materials'},{},'',1,key='materials/Wood')
        self.assertEqual(a['license'],'CC0-1.0');self.assertEqual(a['previews'][0]['url'],'https://lazytextures.net:3000/Assets/Wood/Preview.png')
        self.assertEqual({f['filename'] for f in a['files']},{'Wood.png','Wood.zip'});self.assertTrue(a['revision'])
    def test_archive_preserves_a_many_file_item_tail_and_pack_members(self):
        class Fixture(HTTP):
            def json(self,url):
                if '/advancedsearch.php?' in url:return {'response':{'numFound':1,'docs':[{'identifier':'sounds'}]}}
                return {'metadata':{'title':'Forest sounds','licenseurl':'https://creativecommons.org/publicdomain/zero/1.0/'},'files':[{'name':str(i)+'.wav','source':'original','size':'100','md5':str(i)} for i in range(5)]+[{'name':'cover.png','source':'original'}]}
        s={'id':'archive','media':'audio'};first=internet_archive(Fixture(),s,{},'',2);second=internet_archive(Fixture(),s,{},first['next'],2);last=internet_archive(Fixture(),s,{},second['next'],2)
        self.assertEqual([a['key'] for page in (first,second,last) for a in page['items']],['sounds|'+str(i)+'.wav' for i in range(5)])
        self.assertIsNone(last['next'])
        pack=internet_archive(Fixture(),s,{'_pack_key':'sounds'},'',2);self.assertEqual(pack['items'][0]['pack'],'sounds')
    def test_restricted_archive_never_delivers_an_original(self):
        class Fixture(HTTP):
            def json(self,url):return {'metadata':{'access-restricted-item':'true','licenseurl':'https://creativecommons.org/publicdomain/zero/1.0/'},'files':[{'name':'file.wav','source':'original'}]}
        with self.assertRaisesRegex(ValueError,'no longer public'):internet_archive(Fixture(),{'id':'archive','media':'audio'},{},'',1,key='sounds|file.wav')
    def test_every_animation_frame_is_checked_including_a_bad_final_frame(self):
        from PIL import Image
        body=io.BytesIO();Image.new('RGB',(16,16),'green').save(body,format='GIF',save_all=True,append_images=[Image.new('RGB',(16,16),'red')],duration=20,loop=0)
        class Classifier:
            def image(self,path):
                with Image.open(path) as im:bad=im.convert('RGB').getpixel((0,0))[0]>200
                return {'state':'review-required' if bad else 'preview-screened','risk_probability':.5 if bad else 0}
        with tempfile.TemporaryDirectory() as directory,self.assertRaisesRegex(ValueError,'sexual/suggestive'):review_frames(body.getvalue(),'gif',Classifier(),directory)
    def test_unsupported_video_does_not_pass_a_safe_cover(self):
        with tempfile.TemporaryDirectory() as directory,self.assertRaises(Exception):review_frames(b'not video','mp4',object(),directory)
    def test_alternate_vector_is_reviewed_even_after_another_original_passed(self):
        a={'admission':{'safety':{'state':'original-media-screened','sha256':'different-file'}}}
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            path=Path(directory)/'source.svg';path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>evil</script></svg>')
            with patch('infinite_creativity.live_admission.screener',return_value=object()),self.assertRaisesRegex(ValueError,'external/active'):
                check_delivery(a,{'filename':'source.svg','role':'variant','url':'https://example.com/a.svg'},path)
    def test_complete_audio_speech_is_checked_without_retaining_a_transcript(self):
        try:import av
        except ImportError:self.skipTest('optional media decoder not installed')
        import math
        body=io.BytesIO()
        with wave.open(body,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b''.join(struct.pack('<h',int(10000*math.sin(i*.1))) for i in range(16000)))
        class Speech:
            def transcribe(self,*args,**kwargs):return iter([SimpleNamespace(text='clean forest sound')]),SimpleNamespace(language='en')
        with patch('infinite_creativity.live_media_review.speech_model',return_value=Speech()):
            result=review_audio(body.getvalue());self.assertEqual(result['speech_segments'],1);self.assertNotIn('clean forest',json.dumps(result))
        class BadSpeech:
            def transcribe(self,*args,**kwargs):return iter([SimpleNamespace(text='sexual scene')]),SimpleNamespace(language='en')
        with patch('infinite_creativity.live_media_review.speech_model',return_value=BadSpeech()),self.assertRaisesRegex(ValueError,'speech sexual'):review_audio(body.getvalue())
    def test_original_geometry_is_rendered_without_requiring_a_thumbnail(self):
        try:import trimesh
        except ImportError:self.skipTest('optional geometry decoder not installed')
        class Classifier:
            def image(self,path):return {'state':'preview-screened','risk_probability':0}
        body=trimesh.creation.box().export(file_type='glb')
        with tempfile.TemporaryDirectory() as directory:
            result=review_geometry(body,Classifier(),directory);self.assertEqual(result['rendered_views'],6);self.assertEqual(result['triangles'],12)
    def test_animation_pose_evaluator_observes_motion_and_midpoints(self):
        binary=struct.pack('<9f3H2x2f6f',0,0,0,1,0,0,0,1,0,0,1,2,0,1,0,0,0,2,0,0)
        doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36},{'buffer':0,'byteOffset':36,'byteLength':6},{'buffer':0,'byteOffset':44,'byteLength':8},{'buffer':0,'byteOffset':52,'byteLength':24}],
             'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'},{'bufferView':1,'componentType':5123,'count':3,'type':'SCALAR'},{'bufferView':2,'componentType':5126,'count':2,'type':'SCALAR'},{'bufferView':3,'componentType':5126,'count':2,'type':'VEC3'}],
             'nodes':[{'mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}],'animations':[{'samplers':[{'input':2,'output':3}],'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]}
        j=json.dumps(doc).encode();j+=b' '*((-len(j))%4);glb=b'glTF'+struct.pack('<II',2,12+8+len(j)+8+len(binary))+struct.pack('<II',len(j),0x4E4F534A)+j+struct.pack('<II',len(binary),0x004E4942)+binary
        values=list(poses(glb));self.assertEqual(len(values),3);self.assertEqual([float(v[0][0,0]) for v in values],[0,1,2])

if __name__=='__main__':unittest.main()
