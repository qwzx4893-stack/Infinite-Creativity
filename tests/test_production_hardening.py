import asyncio
import hashlib
import json
import socket
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from infinite_creativity import request_scope as runtime
from infinite_creativity.chunk_proofs import attach,read
from infinite_creativity.content import CONTENT_HOSTS,validate_url
from infinite_creativity.live_http import LiveHTTP
from infinite_creativity.live_quality import inspect_source_bundle
from infinite_creativity.live_curation import choose,report
from infinite_creativity.live_admission import Admission
from infinite_creativity.public_transport import PinnedHTTPSConnection,public_addresses


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_reaches_worker_checkpoint_and_cleanup_before_capacity_is_reused(self):
        gate=runtime.Admission(active=1,heavy=1,pending=2);entered=threading.Event();closed=threading.Event()
        def work():
            entered.set()
            try:
                while True:runtime.checkpoint();time.sleep(.005)
            finally:closed.set()
        with patch.object(runtime,'GATE',gate):
            task=asyncio.create_task(runtime.run_blocking(work))
            while not entered.is_set():await asyncio.sleep(.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(closed.is_set());self.assertEqual(gate.metrics()['active'],0);self.assertEqual(gate.pending,0)

    async def test_capacity_rejects_excess_and_cancelled_queued_work_never_enters(self):
        gate=runtime.Admission(active=1,heavy=1,pending=2);release=threading.Event();entered=threading.Event();unexpected=[]
        def work():entered.set();release.wait(2);return 'first'
        with patch.object(runtime,'GATE',gate):
            first=asyncio.create_task(runtime.run_blocking(work))
            while not entered.is_set():await asyncio.sleep(.005)
            second=asyncio.create_task(runtime.run_blocking(lambda:unexpected.append(1)))
            while gate.pending<2:await asyncio.sleep(.005)
            with self.assertRaisesRegex(ValueError,'capacity'):await runtime.run_blocking(lambda:None)
            second.cancel()
            with self.assertRaises(asyncio.CancelledError):await second
            release.set();self.assertEqual(await first,'first')
        self.assertEqual(unexpected,[]);self.assertEqual(gate.pending,0)

    async def test_heavy_work_respects_separate_capacity_and_ordinary_calls_complete(self):
        gate=runtime.Admission(active=2,heavy=1,pending=4);release=threading.Event();entered=threading.Event()
        def heavy():entered.set();release.wait(2)
        with patch.object(runtime,'GATE',gate):
            first=asyncio.create_task(runtime.run_blocking(heavy,heavy=True))
            while not entered.is_set():await asyncio.sleep(.005)
            second=asyncio.create_task(runtime.run_blocking(heavy,heavy=True))
            self.assertEqual(await runtime.run_blocking(lambda:'navigation'),'navigation')
            self.assertEqual(gate.metrics()['heavy'],1)
            release.set();await asyncio.gather(first,second)
        self.assertEqual(gate.pending,0)


class NetworkScopeTests(unittest.TestCase):
    def test_children_share_the_aggregate_transfer_budget(self):
        token=runtime.CURRENT.set(runtime.RequestScope(max_bytes=3))
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                with self.assertRaisesRegex(ValueError,'transfer budget'):
                    list(runtime.context_map(pool,lambda _:runtime.checkpoint(received_bytes=2),[0,1]))
        finally:runtime.CURRENT.reset(token)

    def test_approved_content_hosts_do_not_leak_to_the_next_request(self):
        before=set(CONTENT_HOSTS);a=LiveHTTP();b=LiveHTTP()
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        try:
            with patch('infinite_creativity.content.socket.getaddrinfo',return_value=addresses):
                a.approve_content('https://author-only.example/file')
                validate_url('https://author-only.example/file',hosts=a.hosts)
                with self.assertRaisesRegex(ValueError,'not approved'):validate_url('https://author-only.example/file',hosts=b.hosts)
            self.assertEqual(CONTENT_HOSTS,before)
        finally:a.close();b.close()

    def test_pinned_connection_uses_validated_numeric_address_and_original_tls_name(self):
        calls=[]
        class Socket:
            def settimeout(self,value):pass
            def connect(self,value):calls.append(('connect',value))
            def close(self):pass
        class TLS:
            def wrap_socket(self,raw,server_hostname):calls.append(('tls',server_hostname));return raw
        connection=PinnedHTTPSConnection('author.example');connection._context=TLS()
        with patch('infinite_creativity.public_transport.public_addresses',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]),patch('infinite_creativity.public_transport.socket.socket',return_value=Socket()):
            connection.connect()
        self.assertEqual(calls,[('connect',('8.8.8.8',443)),('tls','author.example')])

    def test_one_private_dns_answer_rejects_the_whole_resolution(self):
        answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('infinite_creativity.public_transport.socket.getaddrinfo',return_value=answers):
            with self.assertRaisesRegex(ValueError,'Private'):public_addresses('author.example',443)


class ChunkProofTests(unittest.TestCase):
    def original(self,root,body):
        path=Path(root)/'original.bin';path.write_bytes(body);file={'_review_key':'selected','url':'https://author.example/original.bin'}
        result={'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)};receipts={'selected':dict(result)}
        attach({'original.bin':(path,file,result)},receipts)
        return file,receipts['selected']

    def test_cross_block_window_only_reads_its_verified_blocks(self):
        body=b'a'*(1024*1024)+b'b'*(1024*1024)+b'c'*(1024*1024);calls=[]
        class Cache:
            def range(self,url,start,length):calls.append((start,length));return body[start:start+length],len(body)
        with tempfile.TemporaryDirectory() as root:
            file,receipt=self.original(root,body);data=read(Cache(),file,receipt,1024*1024-2,6)
        self.assertEqual(data,b'aabbbb');self.assertEqual(calls,[(0,1024*1024),(1024*1024,1024*1024)])

    def test_changed_bytes_and_changed_total_fail_instead_of_falling_back(self):
        body=b'a'*1024
        with tempfile.TemporaryDirectory() as root:
            file,receipt=self.original(root,body)
            for changed,total in [(b'b'*1024,1024),(body,1025)]:
                class Cache:
                    def range(self,*args):return changed,total
                with self.assertRaisesRegex(ValueError,'changed'):read(Cache(),file,receipt,0,12)

    def test_encoded_members_cannot_use_raw_container_ranges(self):
        with tempfile.TemporaryDirectory() as root:
            file,receipt=self.original(root,b'original')
            for kind in ['archive_entry','container_id','tar_entry','json_content_path','transport_encoding']:
                self.assertIsNone(read(None,{**file,kind:'member'},receipt,0,3))

    def test_end_of_file_is_empty_and_out_of_scope_offset_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            file,receipt=self.original(root,b'original')
            self.assertEqual(read(None,file,receipt,8,3),b'')
            with self.assertRaises(ValueError):read(None,file,receipt,9,3)


class SourceCurationTests(unittest.TestCase):
    def source(self,text):return inspect_source_bundle({'component.tsx':{'_text':text}})

    def test_source_fingerprint_ignores_format_comments_but_preserves_rendered_text(self):
        a=self.source('export const Card = () => <div>Hello</div>;')
        b=self.source('// author comment\nexport const Card=()=> <div>Hello</div>;')
        c=self.source('export const Card = () => <div>Goodbye</div>;')
        self.assertEqual(a['normalized_source_sha256'],b['normalized_source_sha256'])
        self.assertNotEqual(a['normalized_source_sha256'],c['normalized_source_sha256'])

    def test_placeholder_component_is_excluded_while_minimal_ui_is_retained(self):
        for text,expected in [('export const Card=()=>null;','excluded'),('export const Card=()=> <span>Ready</span>;','selected')]:
            asset={'kind':'ui-component','software_only':True,'title':'Card','license':'MIT','files':[{'role':'main','bytes':len(text)}],
                   'features':{'source_quality':self.source(text)}}
            card={'id':'selected'};summary=report()
            self.assertEqual(choose(None,asset,card,{},summary,Admission(None)),expected)
            self.assertFalse(card['curation']['professional_guarantee'])

    def test_same_parsed_bundle_with_different_notices_is_not_dropped(self):
        quality=self.source('export const Card=()=> <span>Ready</span>;');gate=Admission(None);summary=report()
        def asset(notice):return {'kind':'ui-component','software_only':True,'title':'Card','license':'MIT','files':[{'role':'main','bytes':50},{'role':'license','sha256':notice}], 'features':{'source_quality':quality}}
        self.assertEqual(choose(None,asset('a'),{'id':'one'},{},summary,gate),'selected')
        self.assertEqual(choose(None,asset('a'),{'id':'two'},{},summary,gate),'excluded')
        self.assertEqual(choose(None,asset('b'),{'id':'three'},{},summary,gate),'selected')

    def test_unknown_visual_domain_is_queued_not_fabricated_high_quality(self):
        asset={'kind':'font','title':'Font','license':'OFL-1.1','files':[{'bytes':100}], 'admission':{'safety':{'state':'metadata-screened'}}}
        card={'id':'font'}
        self.assertEqual(choose(None,asset,card,{},report(),Admission(None)),'queue')

    def test_nonempty_dependencies_cannot_disguise_an_empty_root_component(self):
        quality=inspect_source_bundle({'root.tsx':{'_text':'export const Card=()=>null;','_root':True},
                                      'dependency.tsx':{'_text':'export const Button=()=> <button>Ready</button>;','_root':False}})
        self.assertEqual(quality['substance']['state'],'empty-component')


class MediaProcessTests(unittest.TestCase):
    def test_real_worker_installs_os_resource_limits_before_any_original_parser(self):
        from infinite_creativity.media_process import execute
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'probe.txt';path.write_text('synthetic input')
            result=execute('probe',path,directory)
        self.assertEqual(result['state'],'resource-limits-ready')
        self.assertEqual(result['decoder_isolation']['memory_bytes'],3*1024**3)
        self.assertEqual(result['decoder_isolation']['python_network'],'disabled')

    def test_decoder_environment_does_not_inherit_provider_or_cloud_credentials(self):
        from infinite_creativity.media_process import environment
        with patch.dict(os.environ,{'GITHUB_TOKEN':'synthetic','API_KEY_21ST':'synthetic','AWS_SECRET_ACCESS_KEY':'synthetic','UNRELATED_SECRET':'synthetic'}):
            result=environment(Path(tempfile.gettempdir()))
        for key in ['GITHUB_TOKEN','API_KEY_21ST','AWS_SECRET_ACCESS_KEY','UNRELATED_SECRET']:self.assertNotIn(key,result)

    def test_hard_deadline_kills_an_owned_stuck_decoder(self):
        from infinite_creativity import media_process
        real=subprocess.Popen;processes=[]
        def start(*args,**kwargs):
            process=real([sys.executable,'-c','import time;time.sleep(30)'],**kwargs);processes.append(process);return process
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'probe.txt';path.write_text('synthetic input')
            with patch.object(media_process.subprocess,'Popen',side_effect=start),patch.object(media_process,'limits',return_value={'cpu_seconds':.1}):
                with self.assertRaisesRegex(ValueError,'deadline'):media_process.execute('probe',path,directory)
        self.assertEqual(len(processes),1);self.assertIsNotNone(processes[0].poll())


if __name__=='__main__':unittest.main()
