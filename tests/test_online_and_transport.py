import copy,gzip,io,json,os,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import httpx,numpy as np
from PIL import Image,PngImagePlugin
from infinite_creativity.live_http import LiveHTTP
from infinite_creativity.live_online import poly_pizza,texturecan,museum,incompetech
from infinite_creativity.policy import acceptable,review_terms
from infinite_creativity.vision import Screener
from infinite_creativity.live_providers import github,Providers

class PublicHTTP:
    def __init__(self,responses):self.responses=responses;self.calls=[]
    def text(self,url,*args):self.calls.append(url);return copy.deepcopy(self.responses[url])
    def json(self,url):
        self.calls.append(url)
        for k,v in self.responses.items():
            if url==k or k.endswith('?') and url.startswith(k):return copy.deepcopy(v)
        raise AssertionError('Unexpected test URL: '+url)
    def approve_content(self,url):
        if not url.startswith('https://'):raise ValueError('Public HTTPS required')

class TransportTests(unittest.TestCase):
    def transport(self,handler,hosts=('one.example','two.example')):
        h=LiveHTTP(hosts);h.client=httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False,trust_env=False)
        self.addCleanup(h.close);guard=patch('infinite_creativity.live_http.validate_url');guard.start();self.addCleanup(guard.stop);return h
    def test_parallel_reads_share_one_inflight_request_and_new_scope_is_fresh(self):
        entered=threading.Event();release=threading.Event();count=[]
        def handler(request):count.append(1);entered.set();release.wait(2);return httpx.Response(200,content=b'fresh-one')
        h=self.transport(handler)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(h.read,'https://one.example/data');self.assertTrue(entered.wait(1));second=pool.submit(h.read,'https://one.example/data');release.set()
            self.assertEqual(first.result(),second.result())
        self.assertEqual(len(count),1);self.assertEqual(h.requests,1);h.close();self.assertEqual(h.memo,{})
        other=self.transport(lambda r:httpx.Response(200,content=b'fresh-two'))
        self.assertEqual(other.read('https://one.example/data'),b'fresh-two')
        with self.assertRaisesRegex(ValueError,'closed'):h.read('https://one.example/data')
    def test_redirect_revalidates_host_and_drops_github_authorization(self):
        auth=[]
        def handler(request):
            auth.append(request.headers.get('Authorization'))
            return httpx.Response(302,headers={'Location':'https://two.example/file'}) if request.url.host=='api.github.com' else httpx.Response(200,content=b'ok')
        h=self.transport(handler,('api.github.com','two.example'))
        with patch.dict(os.environ,{'GITHUB_TOKEN':'fixture-only'}):self.assertEqual(h.read('https://api.github.com/data'),b'ok')
        self.assertEqual(auth,['Bearer fixture-only',None])
        h=self.transport(lambda r:httpx.Response(302,headers={'Location':'https://unapproved.example/private'}))
        with self.assertRaisesRegex(ValueError,'Unconfigured'):h.read('https://one.example/data')
    def test_decoded_byte_budget_includes_compressed_responses_and_does_not_cache_failure(self):
        h=self.transport(lambda r:httpx.Response(200,content=gzip.compress(b'x'*100000),headers={'content-encoding':'gzip'}))
        with self.assertRaisesRegex(ValueError,'memory budget'):h.read('https://one.example/data',100)
        self.assertEqual(h.memo,{})
    def test_rate_limit_is_explicit_and_no_retry_sleep_or_snapshot_is_used(self):
        h=self.transport(lambda r:httpx.Response(429,headers={'Retry-After':'60'}))
        with self.assertRaisesRegex(ValueError,'Retry-After=60'):h.read('https://one.example/data')
        self.assertEqual(h.requests,1)
    def test_real_url_guard_rejects_private_network_target(self):
        h=LiveHTTP(['127.0.0.1']);self.addCleanup(h.close)
        with self.assertRaises(ValueError):h.read('https://127.0.0.1/private')

class OnlineContracts(unittest.TestCase):
    def test_british_licence_filename_covers_code_and_explicit_cc0_media_without_mit_inheritance(self):
        class HTTP:
            def json(self,url):
                if '/commits/' in url:return {'sha':'c'*40}
                if '/git/trees/' in url:return {'tree':[{'path':'LICENCE.md','type':'blob','sha':'a'*40,'size':100},{'path':'components/core/button.tsx','type':'blob','sha':'b'*40,'size':50},{'path':'sprites/tree.png','type':'blob','sha':'d'*40,'size':50}],'truncated':False}
                return {'default_branch':'main','license':{'spdx_id':'MIT'}}
            def text(self,*args):return 'Creative Commons Zero v1.0 https://creativecommons.org/publicdomain/zero/1.0/'
        h=HTTP();code={'id':'code','repo':'artist/library','adapter':'github-tree','kind':'ui-component','license_scope_reviewed':True,'path_pattern':r'^components/.*\.tsx$'}
        a=github(h,code,{},'',1)['items'][0];self.assertEqual(a['license'],'MIT');self.assertTrue(a['license_url'].endswith('LICENCE.md'))
        media={**code,'id':'media','adapter':'github-assets','path_pattern':r'^sprites/.*\.png$'}
        self.assertEqual(github(h,media,{},'',1)['items'][0]['license'],'CC0-1.0')
        h.text=lambda *args:'MIT software licence only'
        self.assertEqual(github(h,media,{},'',1)['items'],[])
    def test_generic_collection_alias_cannot_bypass_scoped_contract_or_widen_other_repo_scopes(self):
        sources={'old':{'id':'old','adapter':'github-assets','live_alias_of':'scoped'},'scoped':{'id':'scoped','adapter':'github-pack-library'},'subset':{'id':'subset','adapter':'github-tree','live_alias_of':'code'},'code':{'id':'code','adapter':'github-tree'}}
        providers=Providers(None,sources);self.assertEqual(providers.config('old')['id'],'scoped');self.assertEqual(providers.config('subset')['id'],'subset')
    def poly(self,licence='CC0 1.0',suffix=';'):
        model={'PublicID':'model_1','ResourceID':'a'*8+'-'+'a'*4+'-'+'a'*4+'-'+'a'*4+'-'+'a'*12,'Licence':licence,'Title':'Cartoon tree','Creator':{'Username':'Artist'},'Tags':['tree'],'Tris':120}
        url='https://static.poly.pizza/'+model['ResourceID']+'.glb';script=json.dumps({'initialData':{'model':model,'description':'undefined is text'}})[:-1]+',"empty":undefined}'
        body='<a href="'+url+'">Model</a><script>window.__SERVER_APP_STATE__ = '+script+suffix+'</script>'
        return PublicHTTP({'https://poly.pizza/m/model_1':body}),{'id':'poly','adapter':'poly-pizza'},model
    def test_public_model_uses_item_licence_creator_and_only_exposed_glb(self):
        h,s,d=self.poly('CC-BY 3.0');a=poly_pizza(h,s,{},'',1,key='model_1')
        self.assertEqual(a['license'],'CC-BY-3.0');self.assertEqual(a['author'],'Artist');self.assertIn('Artist',a['features']['attribution']);self.assertEqual(a['files'][0]['role'],'main')
        self.assertFalse(any('token' in u for u in h.calls))
    def test_public_descriptor_is_never_evaluated_and_restricted_rights_are_excluded(self):
        for licence,suffix in [('Premium',';'),('CC0 1.0',"; fetch('https://evil.example/')")]:
            h,s,d=self.poly(licence,suffix)
            with self.assertRaises(ValueError):poly_pizza(h,s,{},'',1,key='model_1')
    def test_paid_advertisements_are_not_model_results(self):
        h,s,d=self.poly();h.responses['https://poly.pizza/api/explore?']={'results':[],'assets':[{'price':99,'publicID':'model_1'}],'count':0}
        self.assertEqual(poly_pizza(h,s,{},'',1)['items'],[])
    def texture(self,rights='Creative Commons CC0 https://creativecommons.org/publicdomain/zero/1.0/'):
        detail='<title>Wood Planks | TextureCan</title><a href="/downloads/wood_0001/wood_0001_1k_public.zip">Download</a><img src="/img/textures/wood_0001/wood_0001_plane_600.png">'
        return PublicHTTP({'https://www.texturecan.com/terms/':rights,'https://www.texturecan.com/details/1/':detail,'https://www.texturecan.com/search/wood/':'<a href="/details/1/">Wood</a><a href="/search/wood/2/">Next</a>'}),{'id':'texture','adapter':'texturecan'}
    def test_material_query_uses_actual_search_and_exposes_licensed_resolution_archive(self):
        h,s=self.texture();result=texturecan(h,s,{'query':'wood'},'',1);a=result['items'][0]
        self.assertEqual(a['license'],'CC0-1.0');self.assertEqual(a['files'][0]['variant'],'1k');self.assertEqual(a['original_access'],'archive-members-require-review');self.assertTrue(result['next'])
        self.assertTrue(any('/search/wood/' in u for u in h.calls))
    def test_revoked_material_rights_do_not_inherit_an_old_cc0_label(self):
        h,s=self.texture('Personal use only')
        with self.assertRaisesRegex(ValueError,'dedication'):texturecan(h,s,{},'',1,key='1')
    def test_pack_members_delegate_to_bounded_internal_archive_navigation(self):
        h,s=self.texture()
        with patch('infinite_creativity.live_public_assets.zip_members',return_value={'items':['map'],'next':None}) as members:
            result=texturecan(h,s,{'_pack_key':'1'},'',1);self.assertEqual(result['items'],['map']);self.assertIn('wood_0001_1k',members.call_args.args[3]['filename'])
    def test_met_uses_current_paginated_api_and_public_domain_flag_per_object(self):
        base='https://collectionapi.metmuseum.org/public/collection/';d={'objectID':7,'title':'Landscape','isPublicDomain':True,'primaryImage':'https://images.metmuseum.org/landscape.jpg','tags':[]}
        h=PublicHTTP({base+'v1.1/search?':{'total':100,'objectIDs':[7]},base+'v1/objects/7':d});s={'id':'met','adapter':'met-open-access'}
        result=museum(h,s,{'query':'landscape'},'',1);self.assertEqual(result['items'][0]['license'],'CC0-1.0');self.assertEqual(result['next'],'1');self.assertTrue(any('/v1.1/search?' in u for u in h.calls))
        h.responses[base+'v1/objects/7']['isPublicDomain']=False
        with self.assertRaisesRegex(ValueError,'eligible'):museum(h,s,{},'',1,key='7')
    def test_cleveland_free_metadata_does_not_authorize_copyrighted_image(self):
        url='https://openaccess-api.clevelandart.org/api/artworks/9';d={'id':9,'title':'Landscape','share_license_status':'Copyrighted','images':{'web':{'url':'https://images.example/art.jpg'}}}
        h=PublicHTTP({url:{'data':[d]}});s={'id':'cma','adapter':'cleveland-open-access'}
        with self.assertRaises(ValueError):museum(h,s,{},'',1,key='9')
        h.responses[url]['data'][0]['share_license_status']='CC0';self.assertEqual(museum(h,s,{},'',1,key='9')['files'][0]['role'],'main')
    def music(self,licence='https://creativecommons.org/licenses/by/4.0/'):
        base='https://incompetech.com/music/royalty-free/';d={'isrc':'USUAN1300023','title':'Discovery Hit','filename':'Discovery Hit.mp3','length':'00:00:15','feel':'uplifting','instruments':'Brass','collection':'42'}
        return PublicHTTP({base+'pieces.json':[d],base+'index.html?isrc=USUAN1300023':'<a href="'+licence+'">License</a><script>const route="/music/royalty-free/mp3-royaltyfree/";</script>'}),{'id':'music','adapter':'incompetech'}
    def test_music_has_current_free_player_contract_credit_and_exact_collection(self):
        h,s=self.music();a=incompetech(h,s,{},'',1,key='USUAN1300023');self.assertEqual(a['features']['declared_technical']['duration'],15);self.assertIn('Kevin MacLeod',a['features']['attribution']);self.assertEqual(a['pack'],'42');self.assertIn('Discovery%20Hit.mp3',a['files'][0]['url'])
        self.assertEqual(incompetech(h,s,{'_pack_key':'other'},'',1)['items'],[])
    def test_music_fails_closed_when_current_free_player_licence_contract_changes(self):
        h,s=self.music('https://example.org/paid-only')
        with self.assertRaises(ValueError):incompetech(h,s,{},'',1,key='USUAN1300023')

class PixelAndPolicyTests(unittest.TestCase):
    def screen(self,path):
        model=Screener.__new__(Screener);model.labels={0:'drawings',1:'hentai',2:'neutral',3:'porn',4:'sexy'};model.input='pixels'
        class Session:
            def run(self,*args):return [np.array([[-100,-100,100,-100,-100]],dtype=np.float32)]
        model.session=Session();return model.image(path)
    def test_decoded_pixels_match_across_png_metadata_encoding_but_preserve_icc_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'one.png';other=Path(directory)/'two.png';pixels=Image.new('RGB',(10,10),'green');pixels.save(path,compress_level=0)
            metadata=PngImagePlugin.PngInfo();metadata.add_text('description','Same art');pixels.save(other,compress_level=9,pnginfo=metadata)
            a=self.screen(path);b=self.screen(other);self.assertNotEqual(a['sha256'],b['sha256']);self.assertEqual(a['decoded_pixel_sha256'],b['decoded_pixel_sha256'])
            pixels.save(other,icc_profile=b'different-color-profile');self.assertNotEqual(a['decoded_pixel_sha256'],self.screen(other)['decoded_pixel_sha256'])
    def test_intentional_sparse_pixel_art_is_not_mistaken_for_empty_transparency(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pixel.png';pixels=Image.new('RGBA',(2048,2048),(0,0,0,0));pixels.putpixel((100,100),(255,255,255,255));pixels.save(path)
            self.assertEqual(self.screen(path)['state'],'preview-screened')
            pixels.putpixel((100,100),(0,0,0,0));pixels.save(path)
            with self.assertRaisesRegex(ValueError,'transparent'):self.screen(path)
    def test_metadata_obfuscation_cannot_hide_sexual_terms(self):
        for value in ('p\u200born','ｈｅｎｔａｉ','p0rn_character','s3x_character','nüde','جِنْسي'):
            self.assertFalse(acceptable(value),value)
        self.assertTrue(review_terms('sugge\u200bstive'));self.assertTrue(acceptable('Middlesex landscape and Sussex architecture'))

if __name__=='__main__':unittest.main()
