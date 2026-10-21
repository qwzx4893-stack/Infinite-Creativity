import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp import types
from mcp.shared.exceptions import McpError


class ProtocolCancellation(unittest.TestCase):
    def test_stdio_cancel_notification_stops_worker_and_cleans_its_scope(self):
        code='''import os,time
from pathlib import Path
from infinite_creativity import live_server
from infinite_creativity.request_scope import checkpoint
marker=Path(os.environ['IC_TEST_MARKER'])
class Library:
 def __enter__(self):return self
 def __exit__(self,*args):marker.with_suffix('.closed').write_text('closed')
 def open(self,**kwargs):
  marker.write_text(str(live_server.mcp.get_context().request_context.request_id))
  while True:checkpoint();time.sleep(.01)
live_server.LiveLibrary=Library
live_server.mcp.run(transport='stdio')
'''
        async def check(root):
            marker=Path(root)/'worker.marker'
            parameters=StdioServerParameters(command=sys.executable,args=['-c',code],env={**os.environ,'IC_TEST_MARKER':str(marker)},cwd=root)
            async with stdio_client(parameters) as (read,write),ClientSession(read,write) as session:
                await session.initialize()
                task=asyncio.create_task(session.call_tool('open_library',{'source':'controlled-fixture'}))
                for _ in range(300):
                    if marker.exists():break
                    await asyncio.sleep(.01)
                self.assertTrue(marker.exists())
                request_id=int(marker.read_text())
                await session.send_notification(types.ClientNotification(types.CancelledNotification(params=types.CancelledNotificationParams(requestId=request_id,reason='Controlled protocol cancellation'))))
                for _ in range(300):
                    if marker.with_suffix('.closed').exists():break
                    await asyncio.sleep(.01)
                self.assertTrue(marker.with_suffix('.closed').exists(),'Cancelled SDK request left its worker running')
                task.cancel()
                with self.assertRaises((asyncio.CancelledError,McpError)):await task
                result=await session.call_tool('library_diagnostics',{})
                self.assertFalse(result.isError)
                admission=result.structuredContent['runtime']['admission']
                self.assertEqual(admission['active'],1) # The diagnostic itself.
                self.assertEqual(admission['queued'],0)
        with tempfile.TemporaryDirectory() as directory:asyncio.run(check(directory))


if __name__=='__main__':unittest.main()
