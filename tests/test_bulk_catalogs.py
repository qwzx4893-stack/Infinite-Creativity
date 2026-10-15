import copy,gzip,hashlib,io,json,tarfile,unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from infinite_creativity.live_bulk import pd3m,objaverse,position,PD_MARK
from infinite_creativity.live_instruments import instruments
from infinite_creativity.live_media_review import original_bytes
from infinite_creativity.live import LiveLibrary,seal
from infinite_creativity.organization import classify


class RowsHTTP:
    def __init__(self,rows,total=3301062):self.rows=rows;self.total=total;self.calls=[]
    def json(self,url):
        self.calls.append(url);params=parse_qs(urlsplit(url).query);offset=int(params['offset'][0]);length=int(params['length'][0])
        return {'num_rows_total':self.total,'rows':[{'row_idx':offset+i,'row':copy.deepcopy(x),'truncated_cells':[]} for i,x in enumerate(self.rows[:length])]}
    def approve_content(self,url):self.calls.append(url)


def picture(**extra):
    return {'id':'a'*32,'url':'https://pd12m.s3.us-west-2.amazonaws.com/images/12345678-1234-1234-1234-123456789abc.jpeg',
            'caption':'A photograph of a colorful mountain landscape','width':1600,'height':1200,'mime_type':'image/jpeg',
            'hash':'b'*32,'license':'https://creativecommons.org/publicdomain/mark/1.0/','source':'Museum',**extra}


class PD3MContracts(unittest.TestCase):
    source={'id':'pd3m','adapter':'pd3m'}
    def test_millionth_row_is_fetched_directly_without_prior_pages_or_global_search(self):
        h=RowsHTTP([picture()]);r=pd3m(h,self.source,{'catalog_offset':2000000},'',1)
        self.assertEqual(r['items'][0]['key'],'2000000:'+'a'*32);self.assertEqual(r['next'],'2000001')
        self.assertEqual(r['catalog']['provider_rows'],3301062);self.assertIsNone(r['catalog']['admitted_unique_assets'])
        self.assertEqual(len([u for u in h.calls if 'datasets-server' in u]),1);self.assertIn('/rows?',h.calls[0])
    def test_public_domain_mark_is_not_relabeled_as_cc0_and_metadata_licence_is_separate(self):
        a=pd3m(RowsHTTP([picture()]),self.source,{},'',1)['items'][0]
        self.assertEqual(a['license'],PD_MARK);self.assertEqual(a['features']['metadata_license'],'CDLA-Permissive-2.0')
        self.assertEqual(a['files'][0]['md5'],'b'*32)
        b=pd3m(RowsHTTP([picture(license='https://creativecommons.org/publicdomain/zero/1.0/')]),self.source,{},'',1)['items'][0]
        self.assertEqual(b['license'],'CC0-1.0')
    def test_caption_safety_rights_resolution_and_remote_routes_are_filtered_before_emission(self):
        variants=[picture(license='https://creativecommons.org/licenses/by-nc/4.0/'),picture(width=128),picture(caption='Sexual suggestive scene'),picture(url='https://127.0.0.1/images/picture.jpg')]
        for x in variants:
            with self.subTest(x=x):self.assertEqual(pd3m(RowsHTTP([x]),self.source,{},'',1)['items'],[])
    def test_selected_row_identity_is_rechecked_and_missing_or_moved_record_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'moved'):pd3m(RowsHTTP([picture(id='c'*32)]),self.source,{},'',1,key='100:'+'a'*32)
        with self.assertRaisesRegex(ValueError,'fails'):pd3m(RowsHTTP([]),self.source,{},'',1,key='100:'+'a'*32)
    def test_continuation_does_not_skip_rows_after_returned_limit_and_keeps_empty_windows(self):
        r=pd3m(RowsHTTP([picture(width=256),picture(),picture(id='c'*32)]),self.source,{},'',1)
        self.assertEqual(r['next'],'2');self.assertEqual(len(r['items']),1)
        empty=pd3m(RowsHTTP([picture(caption='A black and white train photograph')]),self.source,{'query':'botanical'},'',1)
        self.assertEqual(empty['items'],[]);self.assertEqual(empty['next'],'1');self.assertIn('not global',empty['catalog']['query_scope'])
    def test_incomplete_caption_or_noncontiguous_response_is_rejected(self):
        h=RowsHTTP([picture()]);original=h.json
        def truncated(url):
            d=original(url);d['rows'][0]['truncated_cells']=['caption'];return d
        h.json=truncated;self.assertEqual(pd3m(h,self.source,{},'',1)['items'],[])
        def wrong(url):
            d=original(url);d['rows'][0]['row_idx']=8;return d
        h.json=wrong
        with self.assertRaisesRegex(ValueError,'Non-contiguous'):pd3m(h,self.source,{},'',1)
    def test_image_checksum_is_enforced_on_actual_original_bytes(self):
        a=pd3m(RowsHTTP([picture()]),self.source,{},'',1)['items'][0]
        class Bytes:
            def read(self,*args):return b'changed-original'
        with self.assertRaisesRegex(ValueError,'checksum'):original_bytes(Bytes(),a,a['files'][0])
    def test_positions_reject_bool_negative_float_and_excessive_values(self):
        for value in (True,-1,1.5,'1:2',100000001):
            with self.assertRaises(ValueError):position(value)


UID='a'*32
def model(**extra):
    return {'uid':UID,'name':'Stylized low poly tree','license':'by','isAgeRestricted':False,'likeCount':30,'staffpickedAt':None,
            'tags':[{'name':'low-poly'},{'name':'tree'}],'categories':[{'name':'nature'}],'description':'Stylized game prop',
            'faceCount':24,'vertexCount':30,'animationCount':0,'user':{'uid':'artist1','displayName':'Artist'},'archives':{'glb':{'textureCount':0}},**extra}


class ModelHTTP:
    def __init__(self,archive=None,current=None):
        self.archive=archive or model();self.current=current or {**model(),'license':{'slug':'by','url':'https://creativecommons.org/licenses/by/4.0/'},'isDownloadable':True};self.calls=[]
    def json(self,url):
        self.calls.append(url)
        if '/tree/' in url:return [{'type':'file','path':'metadata/000-000.json.gz'},{'type':'file','path':'metadata/000-001.json.gz'}]
        return copy.deepcopy(self.current)
    def read(self,url,*args):self.calls.append(url);return gzip.compress(json.dumps({UID:self.archive}).encode())
    def approve_content(self,url):self.calls.append(url)


class ObjaverseContracts(unittest.TestCase):
    source={'id':'objaverse-curated','adapter':'objaverse-curated'}
    def test_curated_lowpoly_untextured_model_retains_individual_rights_and_public_original(self):
        h=ModelHTTP();a=objaverse(h,self.source,{},'',1)['items'][0]
        self.assertEqual(a['license'],'CC-BY-4.0');self.assertIn('/glbs/000-000/'+UID+'.glb',a['files'][0]['url'])
        self.assertEqual(a['features']['declared_technical']['texture_count'],0)
        self.assertFalse(any('download?' in u or 'object-paths' in u or 'token' in u for u in h.calls))
    def test_current_license_creator_age_availability_and_curator_evidence_cannot_be_bypassed(self):
        for override in ({'license':{'slug':'by-nc','url':'https://creativecommons.org/licenses/by-nc/4.0/'}},{'user':{'uid':'other'}},{'isAgeRestricted':True},{'isDownloadable':False},{'likeCount':0}):
            h=ModelHTTP();h.current.update(override)
            with self.subTest(override=override):
                with self.assertRaises(ValueError):objaverse(h,self.source,{},'',1,key='000-000:'+UID)
    def test_archived_restrictions_and_no_curator_signal_are_filtered_without_current_lookup(self):
        for override in ({'license':'by-nc'},{'isAgeRestricted':True},{'likeCount':1},{'description':'Erotic scene'}):
            h=ModelHTTP(archive=model(**override));r=objaverse(h,self.source,{},'',1)
            self.assertEqual(r['items'],[]);self.assertEqual(r['next'],'1:0');self.assertFalse(any('api.sketchfab.com' in u for u in h.calls))
    def test_partition_jump_is_direct_and_does_not_fetch_other_shards(self):
        h=ModelHTTP();r=objaverse(h,self.source,{'catalog_partition':1},'',1)
        self.assertEqual(r['catalog']['partition'],1);self.assertTrue(any('/metadata/000-001.' in u for u in h.calls))
        self.assertFalse(any('/metadata/000-000.' in u for u in h.calls))
        with self.assertRaisesRegex(ValueError,'within'):objaverse(ModelHTTP(),self.source,{'catalog_partition':2},'',1)
    def test_current_model_failure_is_visible_and_query_scope_is_explicit(self):
        h=ModelHTTP();h.current['isDownloadable']=False;r=objaverse(h,self.source,{},'',1)
        self.assertTrue(r['item_errors']);self.assertIn('not a global',r['catalog']['query_scope'])
    def test_gzip_metadata_has_an_independent_decoded_memory_bound(self):
        h=ModelHTTP();h.read=lambda *args:gzip.compress(b' '* (48*1024*1024+1))
        with self.assertRaisesRegex(ValueError,'decompression'):objaverse(h,self.source,{},'',1,key='000-000:'+UID)


class InstrumentContracts(unittest.TestCase):
    def setup_http(self,licence='CC0 1.0 Universal'):
        prefix='systems/instruments/meta-piano';files=[{'path':p,'type':'blob','sha':str(i+1)*40,'size':50} for i,p in enumerate(['LICENSE',prefix+'/manifest.json',prefix+'/ogg/Piano_C4.ogg'])]
        class HTTP:
            def json(self,url):
                if '/commits/' in url:return {'sha':'c'*40}
                if url.endswith('/catalog.json'):return {'collections':[{'id':'meta-piano','path':prefix,'name':'Piano','tags':['piano']}]}
                return {'id':'meta-piano','category':'instruments','format':'wav','bit_depth':24,'sample_rate':48000,'samples':[{'file':'Piano_C4.wav'},{'file':'Piano_C4.wav'},{'file':'Missing.wav'}]}
            def text(self,*args):return licence
        return HTTP(),files
    def test_actual_ogg_membership_real_packs_and_no_missing_wav_or_duplicate_samples(self):
        h,tree=self.setup_http()
        with patch('infinite_creativity.live_instruments.complete_tree',return_value=tree):r=instruments(h,{'id':'sound'}, {},'',10)
        self.assertEqual(len(r['items']),1);a=r['items'][0];self.assertEqual(a['pack'],'meta-piano');self.assertEqual(a['formats'],['ogg'])
        self.assertEqual(len(a['files']),2);self.assertEqual(a['features']['publisher_master_specification']['bit_depth'],24)
        self.assertEqual(classify({'kind':'audio','title':a['title'],'tags':a['tags'],'upstream_id':a['key']})[0],'audio/instruments')
    def test_exact_pack_scope_and_current_cc0_are_required(self):
        h,tree=self.setup_http()
        with patch('infinite_creativity.live_instruments.complete_tree',return_value=tree):
            self.assertEqual(instruments(h,{'id':'sound'},{'_pack_key':'other'},'',10)['items'],[])
            with self.assertRaises(ValueError):instruments(h,{'id':'sound'}, {},'',1,key='other/Piano_C4')
        h,tree=self.setup_http('Personal use only')
        with patch('infinite_creativity.live_instruments.complete_tree',return_value=tree):
            with self.assertRaisesRegex(ValueError,'CC0'):instruments(h,{'id':'sound'}, {},'',1)
    def test_photography_is_separate_from_illustration_and_sound_tracks(self):
        a={'kind':'image','title':'Mountain','tags':['photography'],'upstream_id':'1'}
        self.assertEqual(classify(a)[0],'two-d/photography');a.update(kind='illustration',tags=['painting']);self.assertEqual(classify(a)[0],'two-d/illustrations')


class TransitionContracts(unittest.TestCase):
    def package(self,declaration='MIT'):
        output=io.BytesIO();shader=('// License: '+declaration+'\nvec4 transition(vec2 uv) { return vec4(uv,0.,1.); }').encode()
        with tarfile.open(fileobj=output,mode='w:gz') as archive:
            for name,body in [('package/LICENSE',b'MIT: Permission is hereby granted, free of charge'),('package/transitions/Bounce.glsl',shader)]:
                info=tarfile.TarInfo(name);info.size=len(body);archive.addfile(info,io.BytesIO(body))
        body=output.getvalue();meta={'dist-tags':{'latest':'1.0'},'versions':{'1.0':{'license':'MIT','dist':{'tarball':'https://registry.npmjs.org/transitions.tgz','shasum':hashlib.sha1(body).hexdigest()}}}}
        class HTTP:
            def json(self,*args):return meta
            def read(self,*args):return body
            def approve_content(self,*args):pass
        return HTTP(),meta
    def test_individual_shader_licence_and_kind_are_enforced_separately_from_package_notice(self):
        from infinite_creativity.live_services import npm_package
        source={'id':'transitions','npm':'gl-transitions','member_extensions':['.glsl'],'member_kind':'video-transition','required_member_license':'MIT'}
        for licence,expected in [('MIT',1),('GPL-3.0',0),('CC-BY-NC-4.0',0)]:
            h,meta=self.package(licence);r=npm_package(h,source,{},'',1);self.assertEqual(len(r['items']),expected)
            if expected:self.assertEqual(r['items'][0]['kind'],'video-transition');self.assertIn('tar_entry',r['items'][0]['files'][0])
    def test_current_package_integrity_must_match_before_members_are_exposed(self):
        from infinite_creativity.live_services import npm_package
        h,meta=self.package();meta['versions']['1.0']['dist']['shasum']='0'*40
        with self.assertRaisesRegex(ValueError,'integrity'):npm_package(h,{'id':'transitions','npm':'gl-transitions'}, {},'',1)


if __name__=='__main__':unittest.main()
