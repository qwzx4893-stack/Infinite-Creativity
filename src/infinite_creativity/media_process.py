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
                if os.name!='nt':
                    # Popen created a new session whose group ID is this PID.
                    # The leader may have hit RLIMIT_CPU/exited while native
                    # descendants remain, so do not gate group cleanup on poll().
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                elif process.poll() is None:process.kill()
                if process.poll() is None:
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


def preview(path,directory,classifier,allowed_paths=()):
    """Render and screen a staged GLB without parsing it in the MCP process."""
    from .request_scope import CURRENT
    root=Path(directory).resolve();path=Path(path).resolve()
    allowed={Path(value).resolve() for value in allowed_paths}
    if not path.is_relative_to(root) or any(not value.is_relative_to(root) for value in allowed):
        raise ValueError('Preview dependency leaves request staging')
    if CURRENT.get() is not None:
        return execute('preview',path,root,allowed_paths=[str(value) for value in sorted(allowed)])
    import struct
    from .selected_review import member_path
    from .live_media_review import render_glb_preview,image_check
    from PIL import Image
    import io
    if path.stat().st_size>limits()['bytes']:raise ValueError('Preview original exceeds byte budget')
    body=path.read_bytes()
    if len(body)<20 or body[:4]!=b'glTF':raise ValueError('Invalid current GLB')
    length=struct.unpack_from('<I',body,12)[0]
    if length>16*1024*1024 or 20+length>len(body):raise ValueError('Invalid current GLB JSON extent')
    document=json.loads(body[20:20+length]);external=False
    for group in ('buffers','images'):
        for entry in document.get(group,[]):
            uri=entry.get('uri','')
            if not uri or uri.startswith('data:'):continue
            member_path(uri);target=(path.parent/uri).resolve()
            if target not in allowed:raise ValueError('Preview dependency is outside the exact approved manifest')
            external=True
    if external:
        import trimesh
        body=trimesh.load(path,force='scene',process=False).export(file_type='glb')
    pixels=render_glb_preview(body)
    with Image.open(io.BytesIO(pixels)) as image:image_check(image,classifier,directory,'selected-preview')
    return {'_preview_bytes':pixels,'scope':'Current scoped GLB and exact declared dependencies; newly rendered pixels screened'}


def audio_excerpt(path,start=0,seconds=12):
    """Keep listening-preview codec work inside the same bounded worker path."""
    from .request_scope import CURRENT
    if CURRENT.get() is not None:
        result=execute('excerpt',path,Path(path).parent,start=start,seconds=seconds)
        return result['_preview_bytes'],result['listening_preview']
    from .live_media_review import audio_excerpt as decode
    return decode(path,start,seconds)


def visual_scores(direction,images):
    """Stage ranking inputs so native image/model work stays in the worker."""
    if not isinstance(direction,str) or not direction.strip() or len(direction)>2048 or not 1<=len(images)<=12:
        raise ValueError('Supply an art direction and 1..12 ranking images')
    if sum(map(len,images))>limits()['bytes']:raise ValueError('Ranking images exceed request byte budget')
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-rank-') as directory:
        paths=[]
        for number,body in enumerate(images):
            path=Path(directory)/f'image-{number}.bin';path.write_bytes(body);paths.append(str(path))
        return execute('rank',paths[0],directory,direction=direction,images=paths)['scores']


def review(path,extension,classifier,directory):
    from .request_scope import CURRENT
    if CURRENT.get() is not None:
        return execute('review',path,directory,extension=extension)
    from .specialized_media import review_path
    return review_path(path,extension,classifier,directory)
