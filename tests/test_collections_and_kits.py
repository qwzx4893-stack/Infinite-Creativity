import base64,copy,hashlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from infinite_creativity.live import LiveLibrary,seal,unseal,source_configs
from infinite_creativity.live_providers import item
from infinite_creativity.live_collections import descriptor_catalog,pack_library,open_asset_archive,safe_path
from infinite_creativity.creative_kit import fit,ranked,build
from infinite_creativity.live_admission import Admission
from infinite_creativity.organization import classify

class CollectionsTests(unittest.TestCase):
    def test_default_routing_prefers_scoped_collection_over_older_generic_repo_alias(self):
        configs=source_configs();library=LiveLibrary(configs=configs)
        self.assertIsNone(configs['collection:jam-ready'].get('live_alias_of'))
        self.assertIn('collection:jam-ready',library.select({'kind':'sprite'}))
        self.assertEqual(configs['media:series-ai/jam-ready-assets']['live_alias_of'],'collection:jam-ready')
    def descriptor(self,**changes):
        return dict({'schemaVersion':1,'id':'forest/tree','name':'Forest Tree','kind':'model','collection':'forest','creator':{'name':'Artist'},'license':'CC-BY-4.0','licenseUrl':'https://creativecommons.org/licenses/by/4.0/','attribution':'Tree by Artist, CC BY 4.0','file':'assets/tree.glb','preview':'thumbnails/tree.png','bytes':100,'sha256':'a'*64,'technical':{'triangles':120},'usage':{'rigTarget':'forest/humanoid','upAxis':'Y'},'tags':['cartoon']},**changes)
    def http(self,descriptors):
        class HTTP:
            def json(self,url):
                if '/commits/' in url:return {'sha':'c'*40}
                if url.endswith('catalog.json'):return copy.deepcopy(descriptors)
                return {'default_branch':'main','private':False}
        return HTTP()
    def test_descriptor_contract_uses_item_rights_checksum_and_immutable_urls(self):
        h=self.http([self.descriptor()]);s={'id':'generated','repo':'owner/library'}
        a=descriptor_catalog(h,s,{},'',1)['items'][0]
        self.assertEqual(a['license'],'CC-BY-4.0');self.assertEqual(a['author'],'Artist');self.assertIn('/'+'c'*40+'/',a['files'][0]['url']);self.assertEqual(a['files'][0]['sha256'],'a'*64)
        self.assertEqual(a['features']['declared_usage']['rigTarget'],'forest/humanoid')
    def test_descriptor_unknown_rights_bad_hash_missing_credit_and_unsupported_schema_are_excluded(self):
        rows=[self.descriptor(id='bad/'+str(i),**change) for i,change in enumerate([{'license':'MIT'},{'sha256':'bad'},{'attribution':''},{'schemaVersion':2}])]
        self.assertEqual(descriptor_catalog(self.http(rows),{'id':'generated','repo':'owner/library'},{},'',10)['items'],[])
    def test_descriptor_changes_are_fetched_again_without_fallback(self):
        rows=[self.descriptor()];h=self.http(rows);s={'id':'g','repo':'owner/library'}
        self.assertEqual(descriptor_catalog(h,s,{},'',1,key='forest/tree')['title'],'Forest Tree');rows[0]['license']='restricted'
        with self.assertRaises(ValueError):descriptor_catalog(h,s,{},'',1,key='forest/tree')
    def pack_http(self,license_text):
        class HTTP:
            calls=[]
            def json(self,url):
                self.calls.append(url)
                if '/commits/' in url:return {'sha':'c'*40}
                if '/git/trees/' in url and '?recursive' not in url:return {'tree':[{'path':'forest','type':'tree','sha':'p'*40}]}
                if '/git/trees/' in url:
                    return {'tree':[{'path':'2D/tiles/License.txt','type':'blob','sha':'l'*40,'size':100},{'path':'2D/tiles/tree.png','type':'blob','sha':'a'*40,'size':100}],'truncated':False}
                return {'default_branch':'main','private':False,'license':{'spdx_id':'MIT'}}
            def text(self,url,*args):return license_text
        return HTTP()
    def test_huge_library_navigation_does_not_fetch_recursive_root_or_grant_media_rights(self):
        h=self.pack_http('CC0');s={'id':'jam','repo':'owner/huge','adapter':'github-pack-library'}
        a=pack_library(h,s,{},'',1)['items'][0]
        self.assertTrue(a['navigation_only']);self.assertEqual(a['license'],'unknown');self.assertFalse(any('?recursive' in u for u in h.calls))
        self.assertEqual(classify({'kind':a['member_kind'],'title':a['title'],'tags':a['tags'],'upstream_id':a['key']})[0],'discovery/collections')
    def test_selected_pack_and_nested_license_scope_work_without_whole_repo_download(self):
        h=self.pack_http('Creative Commons Zero v1.0 https://creativecommons.org/publicdomain/zero/1.0/');s={'id':'jam','repo':'owner/huge','adapter':'github-pack-library'}
        result=pack_library(h,s,{'_pack_key':'forest'},'',1);a=result['items'][0]
        self.assertEqual(a['license'],'CC0-1.0');self.assertEqual(a['pack'],'forest/2D/tiles')
        nested=pack_library(h,s,{'_pack_key':a['pack']},'',1);self.assertEqual(nested['items'][0]['key'],a['key'])
        self.assertNotIn('https://api.github.com/repos/owner/huge/git/trees/'+'c'*40+'?recursive=1',h.calls)
    def test_platform_license_cannot_be_overridden_by_an_embedded_cc0_mention(self):
        h=self.pack_http('RUN Repository Supplemental License. CC0 1.0 Universal in a copied notice.');s={'id':'jam','repo':'owner/huge','adapter':'github-pack-library'}
        with self.assertRaisesRegex(ValueError,'restricted/platform-only'):pack_library(h,s,{'_pack_key':'forest'},'',1)
    def test_pack_search_does_not_turn_restricted_library_into_usable_results(self):
        h=self.pack_http('Personal use only');s={'id':'jam','repo':'owner/huge','adapter':'github-pack-library'}
        result=pack_library(h,s,{'query':'forest','kind':'sprite'},'',1)
        self.assertEqual(result['items'],[]);self.assertTrue(result['repository_errors'])
    def test_archive_labels_cannot_authorize_unknown_or_restricted_creators(self):
        class HTTP:
            def json(self,url):
                if '/commits/' in url:return {'sha':'c'*40}
                if url.endswith('all-assets.json'):return [{'id':'stolen','packId':'p','license':'CC0','publicPath':'assets/stolen.glb','name':'Tree'}]
                if url.endswith('packs.json'):return [{'id':'p','license':'CC0','sourceUrl':'https://unverified.example/asset'}]
                return {'default_branch':'main'}
        self.assertEqual(open_asset_archive(HTTP(),{'id':'archive','repo':'owner/mirror'},{},'',1)['items'],[])
    def test_unsafe_descriptor_paths_are_rejected(self):
        for value in ('../x.glb','/x.glb','https://example.org/x.glb','a\\x.glb','a/../x.glb'):
            with self.assertRaises(ValueError):safe_path(value)

class KitTests(unittest.TestCase):
    def card(self,source,key,**changes):
        return {'id':seal('asset',{'source':source,'key':key}),'source':source,'title':'Cartoon forest '+key,'description':'forest game','styles':['cartoon'],'kind':'model-3d','access':'usable','admission':{},**changes}
    def test_ranked_selection_caps_source_dominance_and_excludes_references_and_folders(self):
        rows=[self.card('one',str(i)) for i in range(4)]+[self.card('two','tree'),self.card('ref','ref',access='reference'),self.card('packs','folder',kind='asset-pack')]
        result,_=ranked([{'items':rows}],'cartoon forest',4,2)
        self.assertEqual(len(result),3);self.assertEqual(sum(a['source']=='one' for a in result),2)
    def test_exact_original_and_canonical_publisher_product_dedup_cross_sources(self):
        a=self.card('first','one',admission={'safety':{'state':'original-media-screened','sha256':'a'*64}});b=self.card('mirror','two',admission={'safety':{'state':'original-media-screened','sha256':'a'*64}})
        result,count=ranked([{'items':[a,b]}],'cartoon',8,8);self.assertEqual(len(result),1);self.assertEqual(count,1)
        a['admission']['dedup_identity']='same-product';b['admission']={'dedup_identity':'same-product','safety':{'sha256':'different'}}
        self.assertEqual(len(ranked([{'items':[a,b]}],'cartoon',8,8)[0]),1)
    def test_compatibility_distinguishes_declared_unknown_and_mismatch(self):
        a={'formats':['glb'],'features':{'declared_usage':{'rigTarget':'rig-a','units':'metres'},'declared_technical':{'rigged':True}}}
        self.assertEqual(fit(a,{'format':'glb','rig_target':'rig-a'})['state'],'declared-compatible')
        self.assertEqual(fit(a,{'rig_target':'rig-b'})['state'],'incompatible')
        self.assertEqual(fit(a,{'animated':True})['state'],'unverified')
    def test_original_digest_dedup_also_applies_when_publishers_have_different_product_ids(self):
        a=self.card('first','one',admission={'dedup_identity':'product-one','safety':{'state':'original-media-screened','sha256':'x'}})
        b=self.card('mirror','two',admission={'dedup_identity':'product-two','safety':{'state':'original-media-screened','sha256':'x'}})
        self.assertEqual(len(ranked([{'items':[a,b]}],'cartoon',8,8)[0]),1)
    def test_shared_cover_image_does_not_merge_distinct_original_models(self):
        a=self.card('first','one',admission={'safety':{'scope':'preview-raster','sha256':'same-cover','decoded_pixel_sha256':'same-pixels'}})
        b=self.card('second','two',admission={'safety':{'scope':'preview-raster','sha256':'same-cover','decoded_pixel_sha256':'same-pixels'}})
        self.assertEqual(len(ranked([{'items':[a,b]}],'cartoon',8,8)[0]),2)
    def test_preview_dimensions_are_never_treated_as_original_dimensions(self):
        a={'formats':['png'],'admission':{'safety':{'state':'preview-screened','dimensions':[4096,4096],'scope':'preview-raster'}}}
        self.assertEqual(fit(a,{'min_width':2048})['state'],'unverified')
        a['admission']['safety']['scope']='original-raster';self.assertEqual(fit(a,{'min_width':2048})['state'],'verified-selected-scope')
    def test_actual_reviewed_geometry_overrides_optimistic_publisher_counts(self):
        a={'formats':['glb'],'features':{'declared_technical':{'triangleCount':10}},'admission':{'safety':{'state':'original-media-screened','evidence':{'triangles':1000}}}}
        self.assertEqual(fit(a,{'max_triangles':100})['state'],'incompatible')
        with self.assertRaises(ValueError):fit(a,{'max_triangles':float('nan')})
    def test_kit_keeps_failures_pending_items_and_continuations_separate(self):
        good=self.card('a','tree')
        class Library:
            sources={}
            def __init__(self,configs=None):pass
            def open(self,**filters):
                if filters.get('kind')=='audio':raise ValueError('source unavailable')
                return {'items':[good],'review_queue':[{'id':'pending'}],'sources':[],'next_cursor':'continue'}
        result=build(Library(),'cartoon forest',[{'label':'props','kind':'model-3d'},{'label':'sound','kind':'audio'}])
        self.assertFalse(result['complete']);self.assertEqual(result['groups'][0]['review_queue'][0]['id'],'pending');self.assertEqual(result['groups'][1]['state'],'unavailable')
    def test_dedup_origin_works_in_admission_without_persistent_registry(self):
        first=item('one','a','Tree','asset-pack','CC0-1.0','https://example.org/license');second=copy.deepcopy(first);second.update(source='mirror',key='b');first['origin_identity']=second['origin_identity']='creator/pack|tree'
        gate=Admission(object())
        self.assertTrue(gate.accept(first));self.assertFalse(gate.accept(second));self.assertEqual(gate.report['duplicates'],1)

if __name__=='__main__':unittest.main()
