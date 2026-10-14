import io,json,os,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from infinite_creativity.live import LiveLibrary,seal
from infinite_creativity.live_admission import Admission,identities
from infinite_creativity.live_catalogs import openverse,commons
from infinite_creativity.live_providers import item,matches
from infinite_creativity.live_services import npm_package
from infinite_creativity.live_search import recommend


def code(source='fixture',key='button.tsx',digest='a'*40,dependency='b'*40):
    a=item(source,key,'Low poly simple button','ui-component','MIT','https://example.com/license',
           'Author',['react','low-poly'],['tsx'],files=[{'url':'https://example.com/'+key,'filename':key,'sha':digest,'role':'main'},
           {'url':'https://example.com/dependency.css','filename':'dependency.css','sha':dependency,'role':'dependency'}],revision='current')
    a['software_only']=True
    return a


class ExpansionTests(unittest.TestCase):
    def test_21st_uses_metadata_search_and_never_returns_premium_code(self):
        from infinite_creativity.live_21st import twentyfirst
        calls=[]
        async def remote(name,*args):
            calls.append(name);return {'components':[{'id':'one','name':'Card','code':'premium original','full_prompt':'protected full prompt'}]},False
        with patch('infinite_creativity.live_21st.read_remote',remote):
            a=twentyfirst(object(),{'id':'21st'},{'mode':'reference'},'',1,key='one')
        self.assertEqual(calls,['search']);self.assertEqual(a['files'],[])
        self.assertNotIn('premium original',json.dumps(a));self.assertNotIn('protected full prompt',json.dumps(a))
    def test_live_text_delivery_blocks_content_even_with_an_ordinary_title(self):
        from infinite_creativity.catalog import Catalog
        from infinite_creativity.library import Library
        from infinite_creativity.content import ContentCache
        a=code();a['files'][0]['filename']='button.tsx'
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            c=Catalog(Path(td)/'fixture.sqlite')
            c.source({'id':'fixture','url':'https://example.com','adapter':'fixture'})
            c.upsert('fixture','button.tsx','Ordinary button','ui-component','https://example.com/button',license='MIT',license_url='https://example.com/license')
            aid=c.search('Ordinary',limit=1)['items'][0]['id'];c.set_details(aid,{'files':[{'url':'https://example.com/button.tsx','filename':'button.tsx','role':'main'}]})
            lib=Library(c);lib.live_policy=True
            with patch.object(ContentCache,'fetch',lambda self,*args,**kwargs:self.store(b'export const message = "sexual content";','button.tsx','text/plain')):
                with self.assertRaisesRegex(ValueError,'content policy'):lib.code(aid)
            lib.close();c.close()
    def test_leaf_categories_never_overlap_a_parent_leaf(self):
        from infinite_creativity.organization import LEAVES,classify
        self.assertFalse(any(a.startswith(b+'/') for a in LEAVES for b in LEAVES if a!=b))
        for title,path in [('Music loop','audio/music/loops'),('Music stems','audio/music/stems'),('Music track','audio/music/tracks')]:
            self.assertEqual(classify({'kind':'audio','title':title,'tags':[],'upstream_id':'fixture'})[0],path)
    def test_admission_blocks_innuendo_in_description_not_only_title(self):
        a=code();a['description']='suggestive lingerie scene'
        gate=Admission(object());self.assertFalse(gate.accept(a));self.assertEqual(gate.report['blocked_metadata'],1)
    def test_exact_bundle_dedup_preserves_different_material_dependencies(self):
        gate=Admission(object());self.assertTrue(gate.accept(code()))
        self.assertFalse(gate.accept(code('mirror','mirror.tsx')))
        self.assertTrue(gate.accept(code('different','different.tsx',dependency='c'*40)))
        self.assertEqual(gate.report['duplicates'],1)
    def test_next_request_rechecks_with_bounded_client_receipts_not_saved_records(self):
        first=Admission(object());first.accept(code());receipts=first.receipts()
        second=Admission(object(),receipts);self.assertFalse(second.accept(code()))
        changed=code(digest='d'*40);changed['revision']='updated';self.assertTrue(second.accept(changed))
        self.assertTrue(all('Low poly' not in x for x in receipts));self.assertLessEqual(len(receipts),384)
    def test_strict_unknown_audio_does_not_leak_through_a_safe_cover(self):
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'},clear=False):
            a=item('audio','one','Forest voice','audio','CC0-1.0','https://example.com/cc0',formats=['wav'],previews=[{'url':'https://example.com/safe-cover.jpg'}])
            gate=Admission(object());self.assertFalse(gate.accept(a));self.assertIn('original-temporal-media-review-required',gate.report['withheld_reasons'])
    def test_missing_classifier_withholds_raster_and_removes_temporary_files(self):
        class HTTP:
            def read(self,*args):return b'not-a-valid-image'
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'IC_SAFETY_MODE':'strict','IC_VISION_MODEL':td}):
            gate=Admission(HTTP());a=item('image','one','Clean illustration','illustration',previews=[{'url':'https://example.com/file.png'}])
            self.assertFalse(gate.accept(a));self.assertEqual(list(Path(td).iterdir()),[])
    def test_current_image_risk_withheld_before_card(self):
        class HTTP:
            def read(self,*args):return b'image bytes'
        class Classifier:
            def image(self,path):return {'state':'review-required','risk_probability':.6}
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}),patch('infinite_creativity.live_admission.screener',return_value=Classifier()):
            a=item('image','one','Ordinary title','illustration',previews=[{'url':'https://example.com/image.jpg'}]);gate=Admission(HTTP())
            self.assertFalse(gate.accept(a));self.assertIn('image-sexual-or-suggestive-risk',gate.report['withheld_reasons'])
    def test_safe_small_pixel_art_is_not_rejected_for_minimal_style(self):
        import base64
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jJ1QAAAAASUVORK5CYII=')
        class HTTP:
            def read(self,*args):return png
        class Classifier:
            def image(self,path):return {'state':'preview-screened','sha256':'verified-original','dimensions':[1,1]}
        # Image verification is independent of classifier risk; use a valid tiny
        # fixture generated by Pillow when the optional package is installed.
        try:
            from PIL import Image
        except ImportError:self.skipTest('optional Pillow not installed')
        b=io.BytesIO();Image.new('RGBA',(1,1),(10,20,30,255)).save(b,'PNG');png=b.getvalue()
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}),patch('infinite_creativity.live_admission.screener',return_value=Classifier()):
            a=item('pixel','one','Minimal pixel art','sprite','CC0-1.0','https://example.com/cc0',formats=['png'],files=[{'url':'https://example.com/original.png','role':'main'}])
            gate=Admission(HTTP());self.assertTrue(gate.accept(a));self.assertEqual(a['admission']['safety']['scope'],'original-raster')
    def test_platforms_are_evidenced_and_unknown_does_not_match_every_platform(self):
        a=item('unknown','shape','Wooden sculpture','model-3d',formats=['glb']);self.assertEqual(a['platforms'],[])
        b=code();self.assertIn('web',b['platforms']);self.assertNotIn('mobile',b['platforms'])
        self.assertFalse(matches(a,{'mode':'all','platform':'mobile'}))
    def test_openverse_uses_exact_per_item_rights_and_keeps_page_tail(self):
        class HTTP:
            def json(self,url):return {'result_count':20,'results':[{'id':str(i),'title':'Trees','license_url':'https://creativecommons.org/licenses/by/2.0/','url':'https://example.com/'+str(i)+'.jpg','mature':i==2,'filetype':'jpg','unstable__sensitivity':[]} for i in range(20)]}
            def approve_content(self,url):return None
        s={'id':'openverse','media':'images'};first=openverse(HTTP(),s,{},'',3);second=openverse(HTTP(),s,{},first['next'],3)
        self.assertEqual(first['next'],'4');self.assertEqual(first['items'][0]['license'],'CC-BY-2.0')
        self.assertFalse(set(x['key'] for x in first['items'])&set(x['key'] for x in second['items']))
    def test_section_route_excludes_known_incompatible_providers(self):
        s={'web':{'id':'web','name':'Web','url':'https://example.com','adapter':'github-tree','sections':['interface']},'media':{'id':'media','name':'3D','url':'https://example.com','adapter':'github-assets','sections':['three-d']}}
        l=LiveLibrary(object(),s);self.assertEqual(l.select({'section':'three-d'}),['media'])
    def test_reviewer_with_extra_but_missing_required_checks_is_rejected(self):
        a=code();a['software_only']=False;a['kind']='audio'
        command=[sys.executable,'-c',"import json,sys; a=json.load(sys.stdin); print(json.dumps({'decision':'allow','revision':a['required_revision'],'checks':['unrelated','technical-quality']}))"]
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'strict','IC_MEDIA_REVIEW_COMMAND':json.dumps(command)}):
            gate=Admission(object());self.assertFalse(gate.accept(a));self.assertIn('reviewer-incomplete-or-rejected',gate.report['withheld_reasons'])
    def test_npm_notice_and_original_code_are_internal_bounded_members(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as tar:
            for path,body in [('package/LICENSE',b'MIT License\nPermission is hereby granted, free of charge'),('package/dist/index.mjs',b'export const motion = 1;')]:
                info=tarfile.TarInfo(path);info.size=len(body);tar.addfile(info,io.BytesIO(body))
        body=data.getvalue()
        class HTTP:
            def json(self,url):return {'dist-tags':{'latest':'1.0'},'versions':{'1.0':{'license':'MIT','dist':{'tarball':'https://example.com/package.tgz'}}}}
            def approve_content(self,url):return None
            def read(self,*args):return body
        s={'id':'string-tune','url':'https://example.com','npm':'fixture','adapter':'npm-package'}
        view=npm_package(HTTP(),s,{},'',3);self.assertEqual(len(view['items']),1)
        a=view['items'][0];self.assertTrue(a['software_only']);self.assertEqual(a['files'][0]['tar_entry'],'package/dist/index.mjs')
        with patch.dict(os.environ,{'IC_SAFETY_MODE':'strict'}):
            l=LiveLibrary(HTTP(),{'string-tune':s});aid=l.open(source='string-tune')['items'][0]['id']
            with l.content(aid) as (lib,i,_):self.assertIn('export const motion',lib.code(i)['text'])


if __name__=='__main__':unittest.main()
