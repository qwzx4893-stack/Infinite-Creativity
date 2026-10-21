"""Regression coverage for native preview/ranking work escaping RPC workers."""
import base64
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from infinite_creativity import media_process,media_worker
from infinite_creativity.request_scope import CURRENT
from infinite_creativity.review_limits import limits


class MediaBoundaryTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','POSIX owned process groups; Windows uses kill-on-close Job Objects')
    def test_worker_exit_still_terminates_its_native_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'probe.txt';path.touch();marker=root/'descendant-survived'
            child="import pathlib,time;time.sleep(1.5);pathlib.Path("+repr(str(marker))+").write_text('unexpected')"
            leader="import json,subprocess,sys;subprocess.Popen([sys.executable,'-c',"+repr(child)+"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);sys.stdin.buffer.read();print(json.dumps({'result':{'state':'done'},'isolation':{}}))"
            real=subprocess.Popen
            def launch(command,**kwargs):return real([sys.executable,'-c',leader],**kwargs)
            with patch.object(media_process.subprocess,'Popen',side_effect=launch):
                self.assertEqual(media_process.execute('probe',path,root)['state'],'done')
            time.sleep(1.8)
            self.assertFalse(marker.exists(),'A native descendant survived its exited worker')

    def test_scoped_glb_preview_dispatches_without_parsing_in_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scene.glb';path.write_bytes(b'not parsed by parent')
            dependency=Path(directory)/'buffer.bin';dependency.write_bytes(b'buffer')
            token=CURRENT.set(object())
            try:
                with patch.object(media_process,'execute',return_value={'_preview_bytes':b'png'}) as run,patch('infinite_creativity.live_media_review.render_glb_preview',side_effect=AssertionError('parent parser entered')):
                    self.assertEqual(media_process.preview(path,directory,object(),[path,dependency])['_preview_bytes'],b'png')
                self.assertEqual(run.call_args.args,('preview',path.resolve(),Path(directory).resolve()))
                self.assertEqual(set(run.call_args.kwargs['allowed_paths']),{str(path.resolve()),str(dependency.resolve())})
            finally:CURRENT.reset(token)

    def test_preview_refuses_a_dependency_outside_staging_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scene.glb';path.touch()
            with patch.object(media_process,'execute') as run:
                with self.assertRaisesRegex(ValueError,'leaves request staging'):
                    media_process.preview(path,directory,None,[Path(directory).parent/'outside.bin'])
                run.assert_not_called()

    def test_local_preview_rejects_unlisted_external_buffer_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            document=json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':'unlisted.bin','byteLength':4}]}).encode()
            path=Path(directory)/'scene.glb';path.write_bytes(b'glTF'+struct.pack('<III',2,20+len(document),len(document))+b'JSON'+document)
            (Path(directory)/'unlisted.bin').write_bytes(b'data')
            with patch('infinite_creativity.live_media_review.render_glb_preview',side_effect=AssertionError('unlisted input reached parser')):
                with self.assertRaisesRegex(ValueError,'exact approved manifest'):
                    media_process.preview(path,directory,None,[path])

    def test_scoped_audio_excerpt_never_calls_parent_codec(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sound.wav';path.touch();token=CURRENT.set(object())
            try:
                with patch.object(media_process,'execute',return_value={'_preview_bytes':b'wave','listening_preview':{'duration_seconds':1}}) as run,patch('infinite_creativity.live_media_review.audio_excerpt',side_effect=AssertionError('parent codec entered')):
                    self.assertEqual(media_process.audio_excerpt(path,2,1),(b'wave',{'duration_seconds':1}))
                self.assertEqual(run.call_args.args,('excerpt',path,path.parent))
                self.assertEqual(run.call_args.kwargs,{'start':2,'seconds':1})
            finally:CURRENT.reset(token)

    def test_scoped_visual_rank_stages_exact_inputs_without_parent_model(self):
        from infinite_creativity.live_visual_rank import scores
        images=[b'first image',b'<svg>second image</svg>'];staged=[]
        def run(action,path,directory,**extra):
            self.assertEqual(action,'rank');self.assertEqual(extra['direction'],'quiet geometric motion')
            staged.extend(Path(value) for value in extra['images'])
            self.assertEqual([value.read_bytes() for value in staged],images)
            self.assertTrue(all(value.is_relative_to(Path(directory)) for value in staged))
            return {'scores':[.2,.8]}
        token=CURRENT.set(object())
        try:
            with patch.object(media_process,'execute',side_effect=run),patch('infinite_creativity.live_visual_rank.model',side_effect=AssertionError('parent model entered')):
                self.assertEqual(scores('quiet geometric motion',images),[.2,.8])
        finally:CURRENT.reset(token)
        self.assertTrue(all(not value.exists() for value in staged))

    def test_rank_worker_rejects_an_input_outside_its_staging_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image.bin';path.write_bytes(b'local')
            configuration={'action':'rank','path':str(path),'directory':directory,'limits':dict(limits()),'direction':'quiet','images':[str(Path(directory).parent/'outside.bin')]}
            with patch.object(media_worker,'isolate',return_value={}),patch.object(media_worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(configuration).encode()))),patch('infinite_creativity.live_admission.screener',side_effect=AssertionError('rank does not need safety model')):
                with self.assertRaisesRegex(ValueError,'outside staged inputs'):media_worker.main()

    def test_excerpt_worker_encodes_sound_without_loading_vision(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sound.bin';path.touch();output=io.StringIO()
            configuration={'action':'excerpt','path':str(path),'directory':directory,'limits':dict(limits()),'start':0,'seconds':1}
            with patch.object(media_worker,'isolate',return_value={'resources':'test'}),patch.object(media_worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(configuration).encode()))),patch.object(media_worker.sys,'stdout',output),patch('infinite_creativity.live_admission.screener',side_effect=AssertionError('audio does not need vision')),patch('infinite_creativity.live_media_review.audio_excerpt',return_value=(b'RIFF-test',{'duration_seconds':1})):
                media_worker.main()
            result=json.loads(output.getvalue())
            self.assertEqual(base64.b64decode(result['result']['_preview_bytes']),b'RIFF-test')
            self.assertEqual(result['result']['listening_preview'],{'duration_seconds':1})


if __name__=='__main__':unittest.main()
