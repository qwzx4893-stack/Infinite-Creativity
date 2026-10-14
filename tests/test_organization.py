import hashlib,json,tempfile,unittest,zipfile,io,struct
from pathlib import Path
from unittest.mock import Mock
from infinite_creativity.catalog import Catalog
from infinite_creativity.library import Library
from infinite_creativity.organization import organize,sections,packs,classify
from infinite_creativity.curation import curate,record
from infinite_creativity.curation import apply_reviews
from infinite_creativity.drive import public_entries
from infinite_creativity.asset_adapters import complete_tree
from infinite_creativity.multipart import MultipartZip
from infinite_creativity.codrops import code_entries, codrops
from unittest.mock import patch

class OrganizationTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.c=Catalog(Path(self.tmp.name)/'catalog.sqlite');self.l=Library(self.c)
    def tearDown(self):self.l.close();self.c.close();self.tmp.cleanup()
    def test_codrops_pack_contains_original_code_and_notice_not_foreign_media(self):
        paths=['index.html','src/index.js','src/shader.frag','img/demo.jpg','fonts/demo.woff','js/vendor/jquery.js','js/three.min.js','LICENSE']
        entries=[{'type':'blob','path':p,'sha':str(i+1)*40,'size':123} for i,p in enumerate(paths)]
        self.assertEqual([e['path'] for e in code_entries(entries)],paths[:3])
        notice=Path(self.tmp.name)/'MIT.txt';notice.write_text('Permission is hereby granted, free of charge\nThe above copyright notice',encoding='utf-8')
        class Data:
            def json(self,url):
                if '/orgs/' in url:return [{'full_name':'codrops/Fixture','name':'Fixture','default_branch':'main','license':{'spdx_id':'MIT'},'stargazers_count':1}]
                if '/commits/' in url:return {'sha':'a'*40}
                if '/git/trees/' in url:return {'tree':entries,'truncated':False}
                raise AssertionError(url)
        with patch('infinite_creativity.codrops.ContentCache.fetch',return_value={'path':str(notice)}):
            self.assertEqual(codrops(self.c,Data(),'run'),1)
        organize(self.c)
        item=self.c.search(source='codrops-demo:Fixture')['items'][0]
        files=self.l.files(item['id'])['files']
        self.assertEqual({f['relative_path'] for f in files},set(paths[:3]+['LICENSE']))
        self.assertEqual(packs(self.c)['items'][0]['records'],1)
        self.assertFalse(self.c.source_info('codrops')['coverage']['whole_provider_indexed'])
    def asset(self,title,kind='model-3d',digest='a'*40,deps=(),mode='usable',revision='1'):
        url='https://example.com/'+title;aid=hashlib.sha256(url.encode()).hexdigest()[:24]
        self.c.upsert('fixture',title,title,kind,url,license='CC0-1.0',license_url='https://example.com/LICENSE',mode=mode,revision=revision,tags=['cartoon'])
        self.c.set_details(aid,{'pack_name':'Cartoon forest','pack_scope':'forest','files':[{'filename':title+'.glb','sha':digest,'role':'main'}]+list(deps)});self.c.db.commit();return aid
    def test_tree_exclusive_placement_and_pack_search(self):
        ids=[self.asset('tree'),self.asset('robot',digest='b'*40),self.asset('button',kind='ui-component',digest='c'*40)]
        organize(self.c)
        roots=sections(self.c)['sections'];self.assertEqual(sum(r['records'] for r in roots),3)
        self.assertEqual(self.c.get(ids[0])['section_id'],'three-d/environments/nature')
        pid=packs(self.c,query='Cartoon')['items'][0]['id']
        view=self.l.open(pack=pid,section='three-d');self.assertEqual(len(view['items']),2)
        self.assertEqual(self.l.pack(pid)['records'],3)
        with self.assertRaises(ValueError):self.l.open(section='three_d')
        self.assertEqual(sections(self.c,'three-d/environments/nature')['sections'],[])
    def test_full_bundle_duplicate_does_not_discard_different_dependencies(self):
        one=self.asset('tree');two=self.asset('copy');third=self.asset('variant',deps=[{'filename':'atlas.png','role':'dependency','sha':'b'*40}])
        result=curate(self.c);self.assertEqual(result['exact_duplicates_hidden'],1)
        alias=one if self.c.get(one).get('duplicate_of') else two
        self.assertFalse(self.c.get(alias)['usable']);self.assertTrue(self.c.get(third)['usable'])
        self.assertEqual(self.c.search()['total'],2)
        self.assertEqual(len(self.c.browse()['items']),2)
        self.assertEqual(self.c.facets()['kind']['model-3d'],2)
    def test_crc_and_filename_alone_never_deduplicate(self):
        a=self.asset('a');b=self.asset('b')
        for aid in [a,b]:self.c.set_details(aid,{'files':[{'filename':'chair.glb','crc32':123,'bytes':20}]})
        self.assertEqual(curate(self.c)['exact_duplicates_hidden'],0)
    def test_quarantine_blocks_all_access_paths_and_revision_invalidates_evidence(self):
        aid=self.asset('chair');record(self.c,aid,safety='review-required',evidence={'vision':{'scope':'preview-raster'}});self.c.db.commit()
        self.assertEqual(self.c.search()['total'],0);self.assertEqual(self.c.seek()['items'],[]);self.assertEqual(self.c.browse()['items'],[])
        with self.assertRaises(ValueError):self.l.files(aid)
        self.asset('chair',revision='2');self.assertTrue(self.c.get(aid)['usable'])
        self.assertFalse(self.c.db.execute('SELECT * FROM curation WHERE asset_id=?',(aid,)).fetchone())
    def test_changed_dependency_bundle_invalidates_review_and_cached_manifest(self):
        aid=self.asset('chair');record(self.c,aid,safety='preview-screened',evidence={'vision':{'scope':'preview-raster'}});self.c.db.commit()
        self.l.files(aid)
        details=self.c.details(aid);details['files'].append({'url':'https://raw.githubusercontent.com/fixture/pack/pinned/atlas.png','filename':'atlas.png','sha':'b'*40,'role':'dependency'})
        self.c.set_details(aid,details);self.c.db.commit()
        self.assertFalse(self.c.db.execute('SELECT * FROM curation WHERE asset_id=?',(aid,)).fetchone())
        self.assertEqual(len(self.l.files(aid)['files']),1)
    def test_innuendo_requires_review_but_breastplate_and_lowpoly_survive(self):
        valid=self.asset('low poly breastplate');self.asset('suggestive pose')
        curate(self.c);self.assertTrue(self.c.get(valid)['usable']);self.assertEqual(self.c.search()['total'],1)
    def test_context_review_is_hash_and_revision_bound(self):
        aid=self.asset('tile');record(self.c,aid,safety='review-required',evidence={'vision':{'sha256':'a'*64,'scope':'original-raster'}});self.c.db.commit()
        item={'asset_id':aid,'revision':'1','media_sha256':'b'*64,'decision':'safe','reviewer':'fixture','reason':'Inspected original tile'}
        with self.assertRaises(ValueError):apply_reviews(self.c,[item])
        item['media_sha256']='a'*64;apply_reviews(self.c,[item]);self.assertTrue(self.c.get(aid)['usable'])
    def test_google_drive_public_parser_never_executes_js_and_rejects_partial_listing(self):
        row=['publicFile01234',['parent012345'],'model.blend','application/octet-stream']
        data=json.dumps([[row]]).replace('"',r'\x22').replace('[',r'\x5b').replace(']',r'\x5d')
        self.assertEqual(public_entries("window['_DRIVE_ivd'] = '"+data+"'; throw new Error('must not run');")[0]['name'],'model.blend')
        with self.assertRaises(ValueError):public_entries("window['_DRIVE_ivd'] = '"+json.dumps([[row]*50]).replace('"',r'\x22')+"';")
    def test_public_quota_page_is_not_treated_as_a_model_or_bypassed(self):
        url='https://drive.usercontent.google.com/download?id=publicFile01234&export=download';aid=self.asset('alien')
        self.c.set_details(aid,{'files':[{'url':url,'filename':'alien.blend','role':'main'}]});self.c.db.commit()
        r=self.l.cache.store(b'<!DOCTYPE html><html><title>Google Drive - Quota exceeded</title></html>','alien.blend')
        (self.l.cache.root/(hashlib.sha256(url.encode()).hexdigest()+'.receipt.json')).write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'quota exhausted'):self.l.file(aid)
        self.assertEqual(self.l.item(aid)['availability']['state'],'provider-quota')
    def test_complete_tree_follows_subtrees_after_truncation(self):
        f=Mock();f.json.side_effect=[{'truncated':True,'tree':[{'type':'blob','path':'partial'}]},{'tree':[{'type':'tree','path':'packs','sha':'child'}]},{'tree':[{'type':'blob','path':'chair.glb','sha':'a'*40}]}]
        result=complete_tree(f,'fixture/pack','root');self.assertEqual([e['path'] for e in result],['packs/chair.glb'])

class MultipartTests(unittest.TestCase):
    def transport(self,corrupt=False):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('audio/example.wav',b'1234567890'*200)
        body=bytearray(stream.getvalue());eocd=body.rfind(b'PK\x05\x06');cd=body.find(b'PK\x01\x02');cut=55
        struct.pack_into('<HH',body,eocd+4,1,1);struct.pack_into('<I',body,eocd+16,cd-cut)
        if corrupt:body[cut+1]^=1
        parts=[bytes(body[:cut]),bytes(body[cut:])]
        class Cache:
            def range(self,url,start,length):p=parts[int(url)];return p[start:start+length],len(p)
        return Cache(),[{'url':str(i),'bytes':len(p)} for i,p in enumerate(parts)]
    def test_member_spans_volumes_and_crc_is_verified(self):
        cache,parts=self.transport()
        with MultipartZip(cache,parts) as z:self.assertEqual(z.read(z.getinfo('audio/example.wav')),b'1234567890'*200)
    def test_corrupt_original_never_returns_silent_data(self):
        cache,parts=self.transport(True)
        with MultipartZip(cache,parts) as z:
            with self.assertRaises(Exception):z.read(z.getinfo('audio/example.wav'))

if __name__=='__main__':unittest.main()
