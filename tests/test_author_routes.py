import copy
import unittest
from unittest.mock import patch
from infinite_creativity.live_registry import public_registry
from infinite_creativity.component_reference import open_reference
from infinite_creativity.live import seal,unseal


class OriginalHTTP:
    def __init__(self):self.calls=[];self.restricted=False
    def json(self,url):
        self.calls.append(url)
        if '/commits/' in url:return {'sha':'c'*40}
        if url.startswith('https://api.github.com/'):
            return {'private':False,'license':{'spdx_id':'MIT'},'default_branch':'main'}
        if url.endswith('/ui.json'):return {'items':[{'name':'signature','type':'registry:ui','files':[{'path':'signature.tsx','type':'registry:ui'}],'registryDependencies':['@author/utils']}]}
        if url.endswith('/lib.json'):return {'items':[{'name':'utils','type':'registry:lib','files':[{'path':'utils.ts','type':'registry:lib'}]}]}
        raise AssertionError('Unexpected registry request')
    def read(self,url,max_bytes,*args):
        self.calls.append(url)
        if url.endswith('/LICENSE'):
            text='MIT License\nPermission is hereby granted, free of charge, to any person obtaining a copy.'
            return (text+' Commons Clause' if self.restricted else text).encode()
        if url.endswith('/signature.tsx'):return b'export const Signature=()=> <button>Sign</button>;'
        if url.endswith('/utils.ts'):return b'export const cn=(s:string)=>s;'
        raise AssertionError('Unexpected original read')


class AuthorRoutes(unittest.TestCase):
    def source(self):return {'id':'registry:fixture','name':'Original Author','repo':'author/components','url':'https://github.com/author/components','adapter':'public-registry',
            'registry_namespace':'@author','registry_repository_files':True,'registry_index':'https://author.example/ui.json',
            'registry_indexes':[{'url':'https://author.example/ui.json','root':'registry/ui'}, {'url':'https://author.example/lib.json','root':'registry/lib'}]}

    def test_original_author_route_fetches_current_pinned_files_and_notices_without_marketplace(self):
        http=OriginalHTTP();asset=public_registry(http,self.source(),{},'',1,key='signature')
        self.assertEqual(len(asset['files']),3)
        self.assertEqual(asset['features']['source_quality']['state'],'syntax-checked')
        self.assertTrue(any('/'+'c'*40+'/registry/ui/signature.tsx' in url for url in http.calls))
        self.assertTrue(all('21st.dev' not in url for url in http.calls))
        self.assertFalse(any('json_content_path' in f for f in asset['files']))

    def test_author_license_restriction_still_blocks_originals(self):
        http=OriginalHTTP();http.restricted=True
        with self.assertRaisesRegex(ValueError,'MIT contract'):public_registry(http,self.source(),{},'',1,key='signature')

    def test_registry_dependency_cannot_escape_its_original_source_root(self):
        http=OriginalHTTP();original=http.json
        def changed(url):
            value=original(url)
            if url.endswith('/ui.json'):value['items'][0]['files'][0]['path']='../outside.tsx'
            return value
        http.json=changed
        with self.assertRaisesRegex(ValueError,'Unsafe'):public_registry(http,self.source(),{},'',1,key='signature')

    def test_reference_resolves_an_explicit_original_author_mapping_without_fetching_the_page(self):
        class Library:
            sources={'original':{'id':'original','adapter':'public-registry','repo':'author/components','reference_authors':['kevingirelli']}}
            def get(self,aid):return {'id':aid,'key':unseal(aid,'asset')['key']}
            def card(self,asset):return asset
        result=open_reference(Library(),'https://21st.dev/@kevingirelli/components/signature')
        self.assertEqual(result['state'],'original-author-source-resolved')
        self.assertEqual(result['item']['key'],'signature')
        self.assertEqual(result['author_repository'],'author/components')

    def test_unconfigured_author_never_becomes_a_fake_completed_integration(self):
        class Library:sources={}
        result=open_reference(Library(),'@unconfigured/button')
        self.assertEqual(result['state'],'independent-author-route-not-configured')
        self.assertNotIn('item',result)

    def test_reference_rejects_credentials_other_hosts_and_path_injection(self):
        class Library:sources={}
        for value in ['https://21st.dev@evil.example/@a/components/b','http://21st.dev/@a/components/b','https://21st.dev/@a/components/%2e%2e','@a/../private']:
            with self.assertRaises(ValueError):open_reference(Library(),value)


if __name__=='__main__':unittest.main()
