import copy,hashlib,io,json,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from infinite_creativity.live import LiveLibrary,seal,unseal,source_configs
from infinite_creativity.live_quality import inspect_source_bundle,score_raster,assess_record,aesthetic_head
from infinite_creativity.live_registry import public_registry,safe_path

NOTICE=b'MIT License\nCopyright Author\nPermission is hereby granted, free of charge, to any person obtaining a copy.'
SOURCE={'id':'registry:test','name':'Author','repo':'author/components','url':'https://author.example','adapter':'public-registry',
        'registry_namespace':'@author','registry_index':'https://author.example/r/registry.json','registry_item':'https://author.example/r/{name}.json','asset_tags':['react']}

def member(name,text='export const Component = () => <button>Ready</button>;',**extra):
    return {'name':name,'type':'registry:ui','title':name.replace('-',' ').title(),'files':[{'path':name+'.tsx','type':'registry:ui','content':text}],**extra}

class RegistryHTTP:
    def __init__(self,items=None):self.items=items or {'fancy-button':member('fancy-button')};self.notice=NOTICE;self.spdx='MIT';self.private=False;self.read_transform=None
    def json(self,url):
        if url.endswith('/r/registry.json'):return {'items':[{'name':n,'type':p['type'],'title':p.get('title',n)} for n,p in self.items.items()]}
        if '/commits/' in url:return {'sha':'c'*40}
        if url.startswith('https://api.github.com/repos/'):return {'private':self.private,'license':{'spdx_id':self.spdx},'default_branch':'main'}
        name=url.split('/r/')[-1].removesuffix('.json')
        if name not in self.items:raise AssertionError('Unexpected registry request')
        return copy.deepcopy(self.items[name])
    def read(self,url,max_bytes,*args):
        if 'raw.githubusercontent.com' in url:return self.notice
        data=self.json(url)
        if self.read_transform:data=self.read_transform(data)
        body=json.dumps(data).encode()
        if len(body)>max_bytes:raise ValueError('Test byte limit')
        return body

class RegistryTests(unittest.TestCase):
    def test_keyless_original_source_dependency_notices_and_request_cleanup(self):
        h=RegistryHTTP({'fancy-button':member('fancy-button',registryDependencies=['utils'],dependencies=['lucide-react']),
                        'utils':{'name':'utils','type':'registry:lib','files':[{'path':'lib/utils.ts','content':'export const cn = (...args: string[]) => args.join(" ");'}]}})
        a=public_registry(h,SOURCE,{'query':'fancy-button','format':'tsx'},'',1)['items'][0]
        self.assertEqual(len(a['files']),3);self.assertEqual(a['features']['source_quality']['parsed_source_files'],2)
        self.assertFalse(any('_text' in f for f in a['files']))
        l=LiveLibrary(h,{SOURCE['id']:SOURCE});aid=seal('asset',{'source':SOURCE['id'],'key':a['key']})
        with l.content(aid) as (lib,local,metadata):
            files=lib.files(local)['files'];original=lib.file(local,next(f['id'] for f in files if f['role']=='main'))
            path=Path(original['path']);self.assertIn(b'<button>',path.read_bytes());self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),original['sha256'])
            self.assertTrue(any(f['role']=='license' for f in files))
        self.assertFalse(path.exists())
    def test_json_delivery_rechecks_exact_content_missing_ambiguous_and_changed(self):
        for mode in ('changed','missing','duplicate'):
            h=RegistryHTTP();aid=seal('asset',{'source':SOURCE['id'],'key':'fancy-button'})
            with LiveLibrary(h,{SOURCE['id']:SOURCE}).content(aid) as (lib,local,a):
                fid=next(f['id'] for f in lib.files(local)['files'] if f['role']=='main')
                def transform(data):
                    if mode=='changed':data['files'][0]['content']='changed'
                    elif mode=='missing':data['files']=[]
                    else:data['files']*=2
                    return data
                h.read_transform=transform
                with self.assertRaises(ValueError):lib.file(local,fid)
    def test_current_private_restrictive_and_non_mit_rights_fail_closed(self):
        for change in ('private','spdx','clause'):
            h=RegistryHTTP()
            if change=='private':h.private=True
            elif change=='spdx':h.spdx='NOASSERTION'
            else:h.notice+=b' Commons Clause'
            with self.assertRaises(ValueError):public_registry(h,SOURCE,{},'',1,key='fancy-button')
    def test_premium_and_orphan_components_are_not_originals(self):
        for flag in ({'premium':True},{'requiresAuth':True},{'access':'paid'},{'license':'proprietary'}):
            h=RegistryHTTP({'fancy-button':member('fancy-button',**flag)})
            with self.assertRaises(ValueError):public_registry(h,SOURCE,{},'',1,key='fancy-button')
        with self.assertRaises(ValueError):public_registry(RegistryHTTP(),SOURCE,{},'',1,key='unlisted')
    def test_dependency_cycles_deduplicate_and_untrusted_urls_are_rejected(self):
        h=RegistryHTTP({'fancy-button':member('fancy-button',registryDependencies=['utils']),
                        'utils':member('utils','export const fn = 1;',registryDependencies=['fancy-button'])})
        self.assertEqual(len(public_registry(h,SOURCE,{},'',1,key='fancy-button')['features']['registry_dependencies']),2)
        h.items['utils']['registryDependencies']=['https://private.example/component.json']
        with self.assertRaisesRegex(ValueError,'independently licensed'):public_registry(h,SOURCE,{},'',1,key='fancy-button')
    def test_base_style_configuration_and_dependencies_are_carried(self):
        h=RegistryHTTP({'fancy-button':member('fancy-button'), 'index':{'name':'index','type':'registry:style','dependencies':['class-variance-authority'],'cssVars':{'theme':{'radius':'1rem'}},'files':[]}})
        a=public_registry(h,SOURCE,{},'',1,key='fancy-button')
        self.assertIn('class-variance-authority',a['features']['npm_dependencies']);self.assertEqual(a['features']['registry_configuration'][0]['name'],'index')
    def test_cross_registry_dependency_requires_its_own_current_rights(self):
        other={**SOURCE,'id':'registry:other','repo':'other/components','url':'https://other.example','registry_namespace':'@other','registry_index':'https://other.example/r/registry.json','registry_item':'https://other.example/r/{name}.json'}
        class Cross(RegistryHTTP):
            deny=False
            def json(self,url):
                if self.deny and url=='https://api.github.com/repos/other/components':return {'private':False,'license':{'spdx_id':'NOASSERTION'},'default_branch':'main'}
                if url=='https://other.example/r/registry.json':return {'items':[{'name':'helper','type':'registry:lib'}]}
                if url=='https://other.example/r/helper.json':return {'name':'helper','type':'registry:lib','files':[{'path':'helper.ts','content':'export const helper = 1;'}]}
                return super().json(url)
        h=Cross({'fancy-button':member('fancy-button',registryDependencies=['@other/helper'])})
        with patch('infinite_creativity.live.source_configs',return_value={SOURCE['id']:SOURCE,other['id']:other}):
            a=public_registry(h,SOURCE,{},'',1,key='fancy-button');self.assertEqual(sum(f['role']=='license' for f in a['files']),2)
            h.deny=True
            with self.assertRaisesRegex(ValueError,'MIT'):public_registry(h,SOURCE,{},'',1,key='fancy-button')
    def test_dependency_graph_budget_is_enforced(self):
        h=RegistryHTTP({str(i):member(str(i),registryDependencies=[str(i+1)] if i<12 else []) for i in range(13)})
        with self.assertRaisesRegex(ValueError,'twelve'):public_registry(h,SOURCE,{},'',1,key='0')
    def test_variants_group_under_one_logical_design(self):
        h=RegistryHTTP({n:member(n) for n in ('Button-JS-CSS','Button-TS-CSS','Button-JS-TW','Button-TS-TW')})
        r=public_registry(h,{**SOURCE,'group_variants':True},{},'',4)
        self.assertEqual(len(r['items']),1);self.assertEqual(r['items'][0]['features']['implementation'],'Button-TS-TW');self.assertEqual(r['catalog']['implementation_variants'],4)
        variant=public_registry(h,{**SOURCE,'group_variants':True},{},'',1,key='Button|Button-JS-CSS')
        self.assertEqual(variant['features']['implementation'],'Button-JS-CSS')
    def test_paths_noncode_conflicts_duplicate_members_and_invalid_syntax_are_rejected(self):
        for path in ('../bad.tsx','/bad.tsx','C:/bad.tsx','a\\bad.tsx'):
            with self.assertRaises(ValueError):safe_path(path)
        for mode in ('media','duplicate','syntax','conflict'):
            h=RegistryHTTP();p=h.items['fancy-button']
            if mode=='media':p['files'][0]['path']='preview.png'
            elif mode=='duplicate':p['files']*=2
            elif mode=='syntax':p['files'][0]['content']='export const = <button>'
            else:
                p['registryDependencies']=['other'];h.items['other']=member('other');h.items['other']['files'][0]['path']='fancy-button.tsx';h.items['other']['files'][0]['content']='export const other = 1;'
            with self.assertRaises(ValueError):public_registry(h,SOURCE,{},'',1,key='fancy-button')
    def test_registry_scope_is_current_public_author_projects_only(self):
        configs=source_configs();r={k:v for k,v in configs.items() if v.get('adapter')=='public-registry'}
        self.assertEqual(len(r),6);self.assertNotIn('registry:react-bits',r);self.assertIn('21st-dev/agent-elements',[v['repo'] for v in r.values()])
        self.assertTrue({'registry:corsair','registry:ui-layouts','registry:uselayouts'}<=r.keys())

class QualityTests(unittest.TestCase):
    def test_ast_imports_ignore_comment_prose_but_report_undeclared_packages(self):
        source='// Task from "phantom"\nimport {X} from "@vendor/ui";\nimport {Y} from "motion/react";\nexport const C = () => <div/>;'
        r=inspect_source_bundle({'c.tsx':{'_text':source}},['@vendor/ui@2'])
        self.assertEqual(r['state'],'syntax-checked');self.assertEqual(r['undeclared_package_imports'],['motion']);self.assertEqual(r['visual_design'],'unverified-no-render')
    def test_invalid_source_rejected_and_css_has_no_fabricated_parser(self):
        self.assertEqual(inspect_source_bundle({'a.tsx':{'_text':'const = <'}})['state'],'rejected')
        r=inspect_source_bundle({'a.css':{'_text':'button{color:red}'}});self.assertEqual(r['state'],'unverified');self.assertEqual(len(r['unparsed']),1)
    def test_aesthetic_head_is_finite_512d_regression_and_not_probability(self):
        data,weights=aesthetic_head();self.assertEqual(weights.shape,(512,));self.assertTrue(np.isfinite(weights).all())
        out=io.BytesIO();Image.new('RGB',(32,48),'blue').save(out,format='PNG');vector=np.zeros(512,dtype=np.float32);vector[0]=1
        with patch('infinite_creativity.live_quality.image_vector',return_value=vector):r=score_raster(out.getvalue())
        self.assertAlmostEqual(r['score'],float(weights[0]+data['bias']),places=3);self.assertIn('not a probability',r['scale']);self.assertEqual(r['dimensions'],[32,48])
    def test_nonphotographic_domains_never_receive_photo_aesthetic_score(self):
        for kind,tags in [('image',['artwork']),('model-3d',[]),('material',[]),('audio',[])]:
            a={'title':'Creative','kind':kind,'tags':tags,'admission':{'safety':{'scope':'original-raster'}}}
            with patch('infinite_creativity.live_quality.score_raster',side_effect=AssertionError('Wrong domain')):
                r=assess_record(None,a,'id')
            self.assertFalse(r['professional_guarantee']);self.assertEqual(r['selection'],'visual-quality-unverified')
    def test_threshold_rejects_invalid_numeric_values(self):
        for n in (True,float('nan'),float('inf'),-1,11,'high'):
            with self.assertRaises(ValueError):assess_record(None,{},'id',n)
    def test_collection_filters_and_cursor_continue_without_promoting_uncertainty(self):
        h=RegistryHTTP({'a':member('a'),'b':member('b','export const B = () => <p>Second component</p>;')});l=LiveLibrary(h,{SOURCE['id']:SOURCE})
        l.curation_mode='useful'
        first=l.open(source=SOURCE['id'],limit=1,_quality_filter=True)
        self.assertEqual(first['items'],[]);self.assertEqual(len(first['quality_queue']),1);self.assertIsNotNone(first['next_cursor'])
        second=l.page(first['next_cursor'],100);self.assertEqual(second['quality_queue'][0]['title'],'B');self.assertIsNone(second['next_cursor'])
        relaxed=l.open(source=SOURCE['id'],limit=1,_quality_filter=True,_require_visual_score=False)
        self.assertEqual(len(relaxed['items']),1);self.assertEqual(relaxed['items'][0]['quality_assessment']['aesthetics']['state'],'unverified')
    def test_low_photo_score_excluded_during_collection(self):
        h=RegistryHTTP();l=LiveLibrary(h,{SOURCE['id']:SOURCE})
        l.curation_mode='useful'
        with patch('infinite_creativity.live_quality.assess_record',return_value={'selection':'below-photo-aesthetic-threshold'}):r=l.open(source=SOURCE['id'],limit=1,_quality_filter=True)
        self.assertFalse(r['items']);self.assertFalse(r['quality_queue']);self.assertEqual(r['quality']['excluded'],1)

if __name__=='__main__':unittest.main()
