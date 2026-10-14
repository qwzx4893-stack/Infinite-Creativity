import asyncio,base64,hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from infinite_creativity.live import LiveLibrary,seal,unseal
from infinite_creativity.live_providers import codrops,ambient
from infinite_creativity.live_providers import github
from infinite_creativity.live_http import LiveHTTP

POLY={'id':'polyhaven','name':'Poly Haven','url':'https://polyhaven.com/','adapter':'polyhaven'}
class Fresh:
    def __init__(self,name='Fresh chair',license=None):self.calls=[];self.name=name
    def json(self,url):
        self.calls.append(url)
        if url.endswith('/assets'):return {'chair':{'name':self.name,'type':2,'authors':{'Artist':''},'tags':['wood']}}
        if '/files/' in url:return {'gltf':{'glb':{'url':'https://cdn.polyhaven.com/fixture.glb','size':4}}}
        raise AssertionError(url)

class LiveTests(unittest.TestCase):
    def test_fresh_item_queries_and_no_index_files(self):
        with tempfile.TemporaryDirectory() as td:
            before=set(Path(td).rglob('*'));first=Fresh('First chair');l=LiveLibrary(first,{'polyhaven':POLY})
            view=l.open(source='polyhaven',limit=1);aid=view['items'][0]['id']
            current=Fresh('Changed upstream chair');other=LiveLibrary(current,{'polyhaven':POLY})
            self.assertEqual(other.item(aid)['title'],'Changed upstream chair')
            self.assertEqual(len(current.calls),2)
            self.assertEqual(set(Path(td).rglob('*')),before)
            self.assertEqual(other.overview()['asset_index'],'none')
    def test_cursor_tampering_and_incompatible_locator_rejected(self):
        token=seal('asset',{'source':'polyhaven','key':'chair'})
        with self.assertRaises(ValueError):unseal(token,'view')
        with self.assertRaises(ValueError):unseal(token[:-3]+'xyz','asset')
    def test_model_exports_form_one_item_with_variant_dependencies(self):
        entries=[{'type':'blob','path':p,'sha':str(i+1)*40,'size':1000} for i,p in enumerate(['LICENSE','assets/GLB/Mage.glb','assets/FBX/Mage.fbx','assets/FBX/Mage.png'])]
        class Data:
            def json(self,url):
                if '/commits/' in url:return {'sha':'c'*40}
                if '/git/trees/' in url:return {'tree':entries,'truncated':False}
                return {'default_branch':'main','license':{'spdx_id':'CC0-1.0'}}
            def text(self,url,max_bytes):return 'CC0 1.0 Universal'
        s={'id':'fixture','repo':'fixture/pack','adapter':'github-assets','path_pattern':r'\.(glb|fbx)$'}
        r=github(Data(),s,{'kind':'model-3d'},'',10)
        self.assertEqual(len(r['items']),1);a=r['items'][0]
        self.assertEqual(set(a['formats']),{'glb','fbx'})
        self.assertTrue(any(v['relative_path']=='assets/FBX/Mage.png' for v in a['files']))
        self.assertTrue(any(v['role']=='license' for v in a['files']))
    def test_large_signed_positions_and_transient_rev_bound_file_ids(self):
        cursor=seal('view',{'filters':{},'positions':{str(i):'packages/core/components/'+str(i)+'/button.tsx' for i in range(300)},'done':[],'turn':0})
        self.assertLess(len(cursor),24000);self.assertEqual(len(unseal(cursor,'view')['positions']),300)
        one=LiveLibrary(Fresh(),{'polyhaven':POLY});aid=one.open(source='polyhaven')['items'][0]['id']
        with one.content(aid) as (l,i,a):first=l.files(i)['files'][0]['id']
        class Changed(Fresh):
            def json(self,url):
                r=super().json(url)
                if '/files/' in url:r['gltf']['glb']['sha256']='f'*64
                return r
        with LiveLibrary(Changed(),{'polyhaven':POLY}).content(aid) as (l,i,a):second=l.files(i)['files'][0]['id']
        self.assertNotEqual(first,second)
    def test_unavailable_source_is_not_fake_empty_complete_library(self):
        s={'id':'restricted','name':'Restricted','url':'https://example.com','adapter':'reference','live_reason':'Explicit permission required'}
        l=LiveLibrary(Fresh(),{'restricted':s});r=l.open(source='restricted')
        self.assertEqual(r['items'],[]);self.assertEqual(r['sources'][0]['status'],'unavailable')
        self.assertIn('permission',r['sources'][0]['reason']);self.assertFalse(r['sources'][0]['snapshot_fallback'])
    def test_codrops_pagination_does_not_discard_provider_page_tail(self):
        class Data:
            def json(self,url):return [{'name':f'Pack{i}','full_name':f'codrops/Pack{i}','default_branch':'main','license':{'spdx_id':'MIT'}} for i in range(100)] if 'page=1' in url else []
        s={'id':'codrops'};ids=[];position=''
        for _ in range(25):
            r=codrops(Data(),s,{},position,4);ids.extend(a['key'] for a in r['items']);position=r['next']
        self.assertEqual(len(ids),100);self.assertEqual(len(set(ids)),100)
    def test_ambient_window_keeps_every_unconsumed_item(self):
        class Data:
            def json(self,url):
                import re
                n=int(re.search(r'offset=(\d+)',url)[1]);return {'foundAssets':[{'assetId':str(i),'displayName':'Wood '+str(i),'dataType':'Material'} for i in range(n,min(n+100,105))]}
        ids=[];position=''
        while True:
            r=ambient(Data(),{'id':'ambientcg'},{},position,9);ids.extend(a['key'] for a in r['items'])
            if r['next'] is None:break
            position=r['next']
        self.assertEqual(len(ids),105);self.assertEqual(len(set(ids)),105)
    def test_request_only_parser_files_are_removed(self):
        l=LiveLibrary(Fresh(),{'polyhaven':POLY});aid=l.open(source='polyhaven')['items'][0]['id']
        with l.content(aid) as (lib,local,a):
            folder=lib.c.path.parent
            self.assertFalse(lib.c.path.exists())
            lib.cache.store(b'bytes','fixture.bin')
            self.assertEqual(lib.c.db.execute('PRAGMA database_list').fetchone()[2],'')
        self.assertFalse(folder.exists())
    def test_default_mcp_starts_without_catalog_or_snapshot(self):
        async def check(td):
            env={**os.environ,'IC_CATALOG_DB':str(Path(td)/'does-not-exist.sqlite')};env.pop('IC_MODE',None)
            async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','infinite_creativity.server'],env=env,cwd=td)) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();response=await session.call_tool('library_overview',{})
                    self.assertFalse(response.isError);self.assertEqual(response.structuredContent['mode'],'live-federated')
                    tools=await session.list_tools();self.assertIn('read_asset_file',{t.name for t in tools.tools})
            self.assertFalse((Path(td)/'state').exists());self.assertFalse((Path(td)/'does-not-exist.sqlite').exists())
        with tempfile.TemporaryDirectory() as td:asyncio.run(check(td))
    def test_native_mcp_preview_reads_bytes_before_request_cleanup(self):
        code='''from unittest.mock import patch
from infinite_creativity.live import LiveLibrary
from infinite_creativity.live_server import mcp
from infinite_creativity.content import ContentCache
import base64
png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jJ1QAAAAASUVORK5CYII=")
class HTTP:
 def json(self,url):
  if url.endswith('/assets'):return {'tile':{'name':'Clean tile','type':1,'tags':['clean']}}
  if '/files/' in url:return {'png':{'url':'https://cdn.polyhaven.com/tile.png','size':len(png)}}
  raise ValueError('Unexpected fixture endpoint')
def fetch(self,url,filename,max_bytes,*args,**kwargs):return self.store(png,filename,'image/png')
factory=lambda:LiveLibrary(HTTP(),{'polyhaven':{'id':'polyhaven','name':'Poly Haven','url':'https://polyhaven.com','adapter':'polyhaven'}})
with patch('infinite_creativity.live_server.LiveLibrary',factory),patch.object(ContentCache,'fetch',fetch):mcp.run(transport='stdio')
'''
        async def check(td):
            async with stdio_client(StdioServerParameters(command=sys.executable,args=['-c',code],env={**os.environ,'TMP':td,'TEMP':td},cwd=td)) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();view=await session.call_tool('open_library',{'source':'polyhaven','limit':1});self.assertFalse(view.isError,str(view.content));data=view.structuredContent or json.loads(view.content[0].text);aid=data['items'][0]['id'];image=await session.call_tool('preview_asset',{'asset_id':aid})
                    self.assertFalse(image.isError);self.assertEqual(image.content[-1].type,'image');self.assertNotIn('path',image.structuredContent)
                    self.assertEqual(base64.b64decode(image.content[-1].data)[:8],b'\x89PNG\r\n\x1a\n')
            self.assertFalse(list(Path(td).glob('infinite-creativity-request-*')))
        with tempfile.TemporaryDirectory() as td:asyncio.run(check(td))

if __name__=='__main__':unittest.main()
