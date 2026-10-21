"""Request-only decoder processes with hard deadlines and OS resource limits."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import threading
import signal
from pathlib import Path
from .request_scope import checkpoint
from .review_limits import limits,progress

DECODERS=threading.BoundedSemaphore(2)


def environment(directory):
    from .live_admission import model_path
    from .live_media_review import speech_path
    from .live_visual_rank import model_path as style_path
    allowed={'SystemRoot','SYSTEMROOT','WINDIR','PATH','ProgramFiles','ProgramFiles(x86)',
             'COMSPEC','PATHEXT','LANG','LC_ALL','LD_LIBRARY_PATH','CAIROCFFI_DLL_DIRECTORIES'}
    env={k:v for k,v in os.environ.items() if k in allowed}
    env.update(HOME=str(directory),USERPROFILE=str(directory),TEMP=str(directory),TMP=str(directory),
               PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',
               IC_VISION_MODEL=str(model_path().resolve()),IC_SPEECH_MODEL=str(speech_path().resolve()),
               IC_STYLE_MODEL=str(style_path().resolve()))
    if os.environ.get('IC_BLENDER_PATH'):env['IC_BLENDER_PATH']=os.environ['IC_BLENDER_PATH']
    return env


def execute(action,path,directory,**extra):
    while not DECODERS.acquire(timeout=.05):checkpoint()
    try:return _execute(action,path,directory,**extra)
    finally:DECODERS.release()

def _execute(action,path,directory,**extra):
    root=Path(directory).resolve();path=Path(path).resolve()
    if not path.is_relative_to(root):raise ValueError('Decoder input leaves request staging')
    configuration={'action':action,'path':str(path),'directory':str(root),'limits':dict(limits()),**extra}
    encoded=json.dumps(configuration).encode()
    if len(encoded)>2*1024*1024:raise ValueError('Decoder configuration exceeds budget')
    started=time.monotonic();seconds=limits()['cpu_seconds']
    command=[sys.executable,'-I','-m','infinite_creativity.media_worker']
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(command,cwd=root,env=environment(root),stdin=subprocess.PIPE,
                              stdout=output,stderr=subprocess.DEVNULL,creationflags=flags,start_new_session=os.name!='nt') as process:
            first=True
            try:
                while True:
                    checkpoint()
                    if time.monotonic()-started>seconds:raise ValueError('Isolated decoder deadline exceeded')
                    try:
                        process.communicate(input=encoded if first else None,timeout=.2)
                        break
                    except subprocess.TimeoutExpired:
                        first=False
                        progress(time.monotonic()-started,seconds,'Isolated original-media review')
            finally:
                if process.poll() is None:
                    if os.name!='nt':
                        try:
                            if os.getpgid(process.pid)==process.pid:os.killpg(process.pid,signal.SIGKILL)
                            else:process.kill()
                        except ProcessLookupError:pass
                    else:process.kill()
                    process.wait(timeout=5)
        output.seek(0);body=output.read(8*1024*1024+1)
    if len(body)>8*1024*1024:raise ValueError('Decoder result exceeds bounded output')
    if process.returncode or not body:raise ValueError('Isolated decoder failed or exceeded an OS resource limit')
    result=json.loads(body)
    if result.get('error'):raise ValueError('Original withheld: '+result['error'][:240])
    evidence=result['result']
    if evidence.get('_preview_bytes'):
        evidence['_preview_bytes']=base64.b64decode(evidence['_preview_bytes'],validate=True)
    if evidence.get('_converted_glb') and not Path(evidence['_converted_glb']).resolve().is_relative_to(root):
        raise ValueError('Decoder output leaves request staging')
    evidence['decoder_isolation']=result['isolation']
    return evidence


class RemoteScreener:
    def __init__(self,path):self.path=path
    def image(self,path):return execute('image',path,Path(path).parent)


def review(path,extension,classifier,directory):
    from .request_scope import CURRENT
    if CURRENT.get() is not None:
        return execute('review',path,directory,extension=extension)
    from .specialized_media import review_path
    return review_path(path,extension,classifier,directory)
