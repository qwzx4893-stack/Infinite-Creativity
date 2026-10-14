import asyncio
import json
import os
import sys
import hashlib
import base64
import io,wave
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from infinite_creativity.catalog import Catalog
from infinite_creativity.content import ContentCache

class MCPTests(unittest.TestCase):
    def test_protocol_search_and_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"catalog.sqlite"
            c=Catalog(path)
            url='https://raw.githubusercontent.com/fixture/pack/pinned/button.tsx'
            c.upsert("fixture","button","minimal button","ui-component","https://example.com/button",license="MIT",license_url="https://example.com/LICENSE",access_url=url)
            aid=hashlib.sha256(b'https://example.com/button').hexdigest()[:24]
            c.set_details(aid,{'files':[{'url':url,'filename':'button.tsx','role':'main'}]})
            from infinite_creativity.organization import organize
            organize(c)
            cache=ContentCache(Path(td)/'content'); body=b'export function Button() { return <button>Save</button> }'
            cached=cache.store(body,'button.tsx','text/plain')
            (cache.root/(hashlib.sha256(url.encode()).hexdigest()+'.receipt.json')).write_text(json.dumps(cached))
            audio_url='https://raw.githubusercontent.com/fixture/pack/pinned/click.wav';audio_id=hashlib.sha256(b'https://example.com/click').hexdigest()[:24]
            c.upsert('fixture','click','interface click','audio','https://example.com/click',license='CC0-1.0',license_url='https://example.com/LICENSE',access_url=audio_url)
            c.set_details(audio_id,{'files':[{'url':audio_url,'filename':'click.wav','role':'main'}]})
            stream=io.BytesIO()
            with wave.open(stream,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*800)
            audio=cache.store(stream.getvalue(),'click.wav','audio/wav')
            (cache.root/(hashlib.sha256(audio_url.encode()).hexdigest()+'.receipt.json')).write_text(json.dumps(audio))
            image_url='https://raw.githubusercontent.com/fixture/pack/pinned/preview.png';study_id=hashlib.sha256(b'https://example.com/study').hexdigest()[:24]
            c.upsert('fixture','study','visual study','visual-reference','https://example.com/study',mode='reference')
            c.set_details(study_id,{'reference_category':'three-d','reference_preview':{'notice':'Presentation study only; no original reuse'},'previews':[{'url':image_url}],'files':[]})
            png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==')
            preview=cache.store(png,'preview.png','image/png')
            (cache.root/(hashlib.sha256(image_url.encode()).hexdigest()+'.receipt.json')).write_text(json.dumps(preview))
            organize(c)
            c.db.commit(); c.close()
            async def run():
                params=StdioServerParameters(command=sys.executable,args=["-m","infinite_creativity.server"],env={**os.environ,"IC_CATALOG_DB":str(path)})
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        names={t.name for t in (await session.list_tools()).tools}
                        self.assertIn("recommend_assets",names)
                        self.assertIn("browse_assets",names)
                        self.assertTrue({'library_sections','library_packs','get_library_pack','preview_audio_asset'}<=names)
                        tree=await session.call_tool('library_sections',{'parent':'interface/components'})
                        leaf=tree.structuredContent['sections'][0]
                        self.assertEqual(leaf['id'],'interface/components/controls')
                        resource=await session.read_resource(leaf['resource_uri'])
                        self.assertEqual(json.loads(resource.contents[0].text)['parent'],leaf['id'])
                        result=await session.call_tool("search_assets",{"query":"button"})
                        self.assertFalse(result.isError)
                        data=result.structuredContent or json.loads(result.content[0].text)
                        self.assertEqual(data["total"],1)
                        links=await session.call_tool("resolve_asset",{"asset_id":data["items"][0]["id"]})
                        self.assertFalse(links.isError)
                        resolved=links.structuredContent or json.loads(links.content[0].text)
                        self.assertEqual(resolved["license"],"MIT")
                        resources=await session.list_resources()
                        self.assertTrue({'creativity://library','creativity://stats','creativity://taxonomy'} <= {str(r.uri) for r in resources.resources})
                        opened=await session.call_tool('open_library',{'query':'button'})
                        self.assertFalse(opened.isError)
                        view=opened.structuredContent
                        self.assertEqual(len(view['items']),1)
                        self.assertTrue(view['items'][0]['resource_uri'].startswith('creativity://asset/'))
                        self.assertNotIn('canonical_url',view['items'][0])
                        collection=(await session.call_tool('create_collection',{'name':'test'})).structuredContent
                        await session.call_tool('add_to_collection',{'collection_id':collection['collection_id'],'asset_ids':[view['items'][0]['id']]})
                        saved=(await session.call_tool('get_collection',{'collection_id':collection['collection_id']})).structuredContent
                        self.assertEqual(saved['total'],1)
                        code=await session.call_tool('read_asset_code',{'asset_id':aid})
                        self.assertFalse(code.isError); self.assertEqual(code.structuredContent['text'],body.decode())
                        manifest=(await session.call_tool('asset_files',{'asset_id':aid})).structuredContent
                        file_id=manifest['files'][0]['id']
                        chunk=(await session.call_tool('read_asset_file',{'asset_id':aid,'file_id':file_id,'length':7})).structuredContent
                        self.assertEqual(base64.b64decode(chunk['data']),body[:7])
                        original=await session.read_resource('creativity://asset/'+aid+'/file/'+file_id)
                        self.assertEqual(base64.b64decode(original.contents[0].blob),body)
                        audio=await session.call_tool('preview_audio_asset',{'asset_id':audio_id})
                        self.assertFalse(audio.isError);self.assertTrue(any(x.type=='audio' for x in audio.content))
                        preview=await session.call_tool('preview_asset',{'asset_id':study_id})
                        self.assertFalse(preview.isError);self.assertTrue(any(x.type=='image' for x in preview.content));self.assertNotIn('path',preview.structuredContent)
                        denied=await session.call_tool('fetch_asset',{'asset_id':study_id})
                        self.assertTrue(denied.isError)
            asyncio.run(asyncio.wait_for(run(),timeout=45))

if __name__ == "__main__": unittest.main()
