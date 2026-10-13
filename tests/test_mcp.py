import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from infinite_creativity.catalog import Catalog

class MCPTests(unittest.TestCase):
    def test_protocol_search_and_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"catalog.sqlite"
            c=Catalog(path)
            c.upsert("fixture","button","minimal button","ui-component","https://example.com/button",license="MIT",license_url="https://example.com/LICENSE",access_url="https://example.com/button.tsx")
            c.db.commit(); c.close()
            async def run():
                params=StdioServerParameters(command=sys.executable,args=["-m","infinite_creativity.server"],env={**os.environ,"IC_CATALOG_DB":str(path)})
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        names={t.name for t in (await session.list_tools()).tools}
                        self.assertIn("recommend_assets",names)
                        self.assertIn("browse_assets",names)
                        result=await session.call_tool("search_assets",{"query":"button"})
                        self.assertFalse(result.isError)
                        data=result.structuredContent or json.loads(result.content[0].text)
                        self.assertEqual(data["total"],1)
                        links=await session.call_tool("resolve_asset",{"asset_id":data["items"][0]["id"]})
                        self.assertFalse(links.isError)
                        resolved=links.structuredContent or json.loads(links.content[0].text)
                        self.assertEqual(resolved["license"],"MIT")
                        resources=await session.list_resources()
                        self.assertEqual(len(resources.resources),2)
            asyncio.run(asyncio.wait_for(run(),timeout=45))

if __name__ == "__main__": unittest.main()
