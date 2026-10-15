import base64,copy,io,json,os,struct,tempfile,threading,unittest,wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from infinite_creativity.live import LiveLibrary,seal
from infinite_creativity.live_providers import item
from infinite_creativity.content import ContentCache
from infinite_creativity.selected_review import review,preview
from infinite_creativity.live_media_review import audio_excerpt
from infinite_creativity.live_admission import Admission
from infinite_creativity.live_health import probe
from infinite_creativity.live_search import batch

class Classifier:
    def image(self,path):return {'state':'preview-screened','risk_probability':0}

class CompleteWorkflows(unittest.TestCase):
    def fixture(self,body=None,filename='art.png',kind='illustration',software=False):
        if body is None:
            stream=io.BytesIO();Image.new('RGB',(16,16),'green').save(stream,format='PNG');body=stream.getvalue()
        url='https://example.org/'+filename;file={'url':url,'filename':filename,'relative_path':filename,'role':'main','bytes':len(body)}
        a=item('fixture','art','Forest art',kind,'MIT' if software else 'CC0-1.0','https://example.org/license',formats=[filename.rsplit('.',1)[-1]],files=[file],revision='current');a['software_only']=software;bodies={url:body}
        class HTTP:
            def read(self,url,*args):return bodies[url]
        library=LiveLibrary(HTTP(),{'fixture':{'id':'fixture','url':'https://example.org','adapter':'github-assets'}});library.providers.get=lambda *args:copy.deepcopy(a)
        return library,seal('asset',{'source':'fixture','key':'art'}),bodies
    def transport(self,bodies,paths,calls):
        def fetch(cache,url,filename='',max_bytes=128*1024*1024,*args,**kwargs):
            calls.append(url)
            if len(bodies[url])>max_bytes:raise ValueError('Fixture exceeds byte budget')
            result=cache.store(bodies[url],filename);paths.append(Path(result['path']));return result
        return patch.object(ContentCache,'fetch',fetch)
    def test_package_inspects_once_and_delivers_the_same_original_and_scoped_manifest(self):
        library,aid,bodies=self.fixture();paths=[];calls=[]
        with self.transport(bodies,paths,calls),patch('infinite_creativity.live_admission.screener',return_value=Classifier()),patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            result=review(library,aid,delivery_length=65536)
        self.assertEqual(len(calls),1);self.assertEqual(base64.b64decode(result['package']['original']['data']),next(iter(bodies.values())))
        self.assertIsNone(result['package']['original']['next_offset']);self.assertEqual(len(result['package']['files']),1);self.assertNotIn('url',result['package']['files'][0]);self.assertTrue(result.get('_preview_png'))
        self.assertFalse(any(p.exists() for p in paths))
    def test_source_package_is_complete_without_loading_media_models_or_executing_code(self):
        body=b'export function Button() { return <button>Save</button> }';library,aid,bodies=self.fixture(body,'button.tsx','ui-component',True);paths=[];calls=[]
        with self.transport(bodies,paths,calls),patch('infinite_creativity.live_admission.screener',side_effect=AssertionError('Source code should not need image models')):
            result=review(library,aid,delivery_length=65536)
        self.assertEqual(base64.b64decode(result['package']['original']['data']),body);self.assertIn('never executed',result['review']['scope']);self.assertEqual(result['license'],'MIT')
        self.assertFalse(any(p.exists() for p in paths))
    def test_obfuscated_sexual_source_is_not_delivered_in_a_code_package(self):
        library,aid,bodies=self.fixture(b'export const text = "s3x_character";','button.tsx','ui-component',True)
        with self.transport(bodies,[],[]),self.assertRaisesRegex(ValueError,'policy'):review(library,aid,delivery_length=65536)
    def test_licence_notice_arrives_with_code_without_another_fetch(self):
        library,aid,bodies=self.fixture(b'export const Button = 1;','button.tsx','ui-component',True);a=library.raw_get(aid);url='https://example.org/LICENCE.md';bodies[url]=b'MIT License\nCopyright 2026 Artist\nPermission is hereby granted.'
        a['files'].append({'url':url,'filename':'LICENCE.md','relative_path':'LICENCE.md','role':'license','bytes':len(bodies[url])});library.providers.get=lambda *args:copy.deepcopy(a);calls=[]
        with self.transport(bodies,[],calls):result=review(library,aid,delivery_length=65536)
        self.assertEqual(len(calls),2);self.assertEqual(result['package']['notices'][0]['text'],bodies[url].decode());self.assertEqual(result['package']['notices'][0]['filename'],'LICENCE.md')
    def test_fast_receipt_preview_still_fetches_and_checks_exact_bytes_before_rendering(self):
        import trimesh
        library,aid,bodies=self.fixture(trimesh.creation.box().export(file_type='glb'),'box.glb','model-3d');paths=[];calls=[]
        with self.transport(bodies,paths,calls),patch('infinite_creativity.live_admission.screener',return_value=Classifier()),patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            approved=review(library,aid)['asset_id']
            with patch('infinite_creativity.selected_review.review_path',side_effect=AssertionError('Unchanged bytes must not repeat whole-model inspection')):
                result=preview(library,approved)
                self.assertEqual(result['state'],'reviewed-digests-revalidated');self.assertTrue(result['_preview_png'])
                url=next(iter(bodies));bodies[url]=bodies[url][:-1]+bytes([bodies[url][-1]^1])
                with self.assertRaisesRegex(ValueError,'changed since selected review'):preview(library,approved)
        self.assertFalse(any(p.exists() for p in paths))
    def test_long_audio_is_pending_before_download_not_a_fake_admitted_original(self):
        library,aid,bodies=self.fixture(b'not downloaded','song.mp3','audio');a=library.raw_get(aid);a['features']={'declared_technical':{'duration':180}}
        with patch.object(library.http,'read',side_effect=AssertionError('Browsing must not download a known long track')):
            admission=Admission(library.http);self.assertFalse(admission.accept(a));self.assertIn('duration',admission.last_withhold)
    def test_native_audio_excerpt_has_correct_window_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tone.wav';signal=(np.sin(np.arange(64000)*2*np.pi*440/16000)*8192).astype('<i2')
            with wave.open(str(path),'wb') as writer:writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(16000);writer.writeframes(signal.tobytes())
            before=path.read_bytes();body,notice=audio_excerpt(path,1.25,1)
            with wave.open(io.BytesIO(body)) as reader:self.assertEqual(reader.getframerate(),22050);self.assertEqual(reader.getnframes(),22050)
            self.assertEqual(notice['start_seconds'],1.25);self.assertEqual(path.read_bytes(),before)
            for start,seconds in [(float('nan'),1),(0,float('inf')),(0,31),(6,1)]:
                with self.assertRaises(ValueError):audio_excerpt(path,start,seconds)
    def test_health_evidence_separates_preview_pending_and_actual_originals(self):
        class HTTP:
            def metrics(self):return {}
        class Library:
            def __init__(self,configs=None):self.sources=configs or {k:{} for k in ('preview','original','pending','down')};self.http=HTTP()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def open(self,source,**kwargs):
                a={'access':'usable','kind':'material','admission':{'safety':{'scope':'preview-raster','state':'preview-screened'}}}
                if source=='original':a['admission']['safety']={'state':'original-media-screened'}
                return {'items':[a] if source in {'preview','original'} else [],'review_queue':[{}] if source=='pending' else [],'sources':[{'source':source,'status':'unavailable'}] if source=='down' else []}
        result=probe(Library(),['preview','original','pending','down']);states={r['source']:r['state'] for r in result['sources']}
        self.assertEqual(states,{'preview':'preview-or-metadata-sample','original':'original-sample-admitted','pending':'metadata-working-original-pending','down':'unavailable'})
    def test_batched_searches_get_independent_parallel_lifetimes(self):
        barrier=threading.Barrier(2);closed=[]
        class Library:
            sources={'fixture':{}}
            def __init__(self,configs=None):pass
            def open(self,**kwargs):barrier.wait(timeout=2);return {'items':[]}
            def close(self):closed.append(1)
        result=batch(Library(),[{'kind':'model-3d'},{'kind':'audio'}],1)
        self.assertEqual(len(result['searches']),2);self.assertEqual(len(closed),2)
    def test_transient_source_retry_keeps_position_and_exhausted_retry_can_resume_explicitly(self):
        library,aid,bodies=self.fixture(kind='asset-pack');positions=[]
        def page(source,filters,after,limit):
            positions.append(after)
            if len(positions) in {1,3}:raise ValueError('Source transport unavailable')
            a=library.raw_get(aid);a['key']=str(len(positions));return {'items':[a],'next':'member-two' if len(positions)==2 else None}
        library.providers.page=page
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'metadata'}):
            first=library.open(source='fixture',limit=1);self.assertTrue(first['sources'][0]['retry_on_next_page'])
            second=library.page(first['next_cursor'],1);third=library.page(second['next_cursor'],1)
            self.assertIsNone(third['next_cursor']);self.assertTrue(third['resume_cursor'])
            fourth=library.page(third['resume_cursor'],1,retry_sources=['fixture']);self.assertEqual(len(fourth['items']),1)
        self.assertEqual(positions,['','','member-two','member-two'])
    def test_per_item_provider_errors_are_visible_instead_of_a_silent_empty_source(self):
        library,aid,bodies=self.fixture();library.providers.page=lambda *args:{'items':[],'next':None,'item_errors':[{'reason':'licence unavailable'}]*20}
        view=library.open(source='fixture',limit=1);self.assertEqual(len(view['sources'][0]['item_errors']),12);self.assertEqual(view['sources'][0]['item_errors_omitted'],8)
    def test_glb_container_metadata_changes_dedup_but_a_transform_variant_remains_distinct(self):
        import trimesh
        first=trimesh.creation.box().export(file_type='glb');length=struct.unpack_from('<I',first,12)[0];document=json.loads(first[20:20+length]);tail=first[20+length:]
        def changed(generator,translate=False):
            d=copy.deepcopy(document);d.setdefault('asset',{})['generator']=generator
            if translate:d['nodes'][0]['translation']=[1,0,0]
            text=json.dumps(d,indent=2).encode();text+=b' '*(-len(text)%4)
            return struct.pack('<4sII',b'glTF',2,20+len(text)+len(tail))+struct.pack('<II',len(text),0x4e4f534a)+text+tail
        bodies={'https://example.org/one.glb':first,'https://example.org/two.glb':changed('Other exporter'),'https://example.org/three.glb':changed('Other exporter',True)}
        class HTTP:
            def read(self,url,*args):return bodies[url]
        assets=[item('fixture',str(i),'Box','model-3d','CC0-1.0','https://example.org/license',formats=['glb'],files=[{'url':url,'filename':str(i)+'.glb','role':'main','bytes':len(body)}]) for i,(url,body) in enumerate(bodies.items())]
        with patch('infinite_creativity.live_admission.screener',return_value=Classifier()),patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            admission=Admission(HTTP());self.assertTrue(admission.accept(assets[0]));self.assertFalse(admission.accept(assets[1]));self.assertTrue(admission.accept(assets[2]));self.assertEqual(admission.report['duplicates'],1)

if __name__=='__main__':unittest.main()
