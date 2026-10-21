"""Fixed software decoder entry point. Source files are never imported as code."""
import base64
import json
import math
import os
import socket
import sys
from pathlib import Path

_JOB=None


def windows_limits(memory,seconds):
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),
                  ('min_working_set',ctypes.c_size_t),('max_working_set',ctypes.c_size_t),
                  ('active_processes',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(n,ctypes.c_ulonglong) for n in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    job=kernel.CreateJobObjectW(None,None)
    if not job:raise OSError('Cannot create decoder resource job')
    config=Extended();config.basic.flags=0x2000|0x100|0x200|0x2|0x8
    config.basic.process_time=int(seconds*10_000_000);config.basic.active_processes=4
    config.process_memory=memory;config.job_memory=memory
    if not kernel.SetInformationJobObject(job,9,ctypes.byref(config),ctypes.sizeof(config)) or not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
        raise OSError('Cannot enforce decoder resource limits')
    global _JOB
    _JOB=job  # Owned until this worker exits; descendants die with the job.


def isolate(configuration):
    memory=3*1024*1024*1024;seconds=math.ceil(configuration['limits']['cpu_seconds'])+2
    if os.name=='nt':windows_limits(memory,seconds);mechanism='Windows Job Object memory/CPU/process-tree limits'
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
        resource.setrlimit(resource.RLIMIT_CPU,(seconds,seconds))
        resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
        mechanism='POSIX address-space/CPU/file-descriptor limits'
    # Defense in depth for Python decoders. This is not an OS network namespace
    # or filesystem sandbox, and is never described as one.
    def denied(*args,**kwargs):raise OSError('Network access disabled in original-media decoder')
    socket.create_connection=denied;socket.getaddrinfo=denied
    original=socket.socket
    class LocalSocket(original):
        def connect(self,address):
            if self.family in {socket.AF_INET,socket.AF_INET6}:return denied()
            return super().connect(address)
        def connect_ex(self,address):
            if self.family in {socket.AF_INET,socket.AF_INET6}:return denied()
            return super().connect_ex(address)
    socket.socket=LocalSocket
    return {'resources':mechanism,'memory_bytes':memory,'cpu_seconds':seconds,
            'environment':'Minimal allowlist; provider/API credentials removed',
            'python_network':'disabled','filesystem':'Request-scoped path checks; no OS filesystem sandbox claimed'}


def main():
    body=sys.stdin.buffer.read(2*1024*1024+1)
    if len(body)>2*1024*1024:raise ValueError('Oversized decoder request')
    config=json.loads(body);root=Path(config['directory']).resolve();path=Path(config['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Decoder input is outside staged originals')
    isolation=isolate(config)
    from .review_limits import profile,_limits
    with profile('extended' if config['limits']['cpu_seconds']>20 else 'fast'):
        token=_limits.set(config['limits'])
        try:
            from .live_admission import screener,model_path
            action=config['action'];extension=config.get('extension',path.suffix.lstrip('.'))
            audio=extension in {'wav','ogg','mp3','flac','m4a','aac','aiff','aif','opus'}
            classifier=None if audio or action in {'probe','aesthetic'} else screener(str(model_path()))
            if action=='probe':result={'state':'resource-limits-ready','network_guard':True}
            elif action=='aesthetic':
                from .live_quality import score_raster
                result=score_raster(path.read_bytes())
            elif action=='image':result=classifier.image(path)
            elif action=='review':
                from .specialized_media import review_path
                result=review_path(path,extension,classifier,str(root))
            elif action=='original':
                from .live_media_review import review_original
                class BytesHTTP:
                    def read(self,*args):return path.read_bytes()
                result=review_original(BytesHTTP(),config['asset'],classifier)
                if result is None:raise ValueError('No original-media reviewer')
            elif action=='delivery':
                from .live_media_review import check_delivery
                check_delivery(config['asset'],config['file'],path)
                result={'state':'exact-original-reviewed'}
            else:raise ValueError('Unknown decoder action')
        finally:_limits.reset(token)
    if result.get('_preview_bytes'):result['_preview_bytes']=base64.b64encode(result['_preview_bytes']).decode()
    sys.stdout.write(json.dumps({'result':result,'isolation':isolation}));sys.stdout.flush()


if __name__=='__main__':
    try:main()
    except Exception as error:
        sys.stdout.write(json.dumps({'error':str(error)[:240]}));sys.stdout.flush()
