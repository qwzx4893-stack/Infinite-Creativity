"""Per-request review budgets, with an explicit larger selected-file path."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
FAST={'bytes':32*1024*1024,'audio_seconds':90,'frames':240,'triangles':120000,'poses':48,'cpu_seconds':20,'pixels':40000000,'layers':128}
EXTENDED={'bytes':512*1024*1024,'audio_seconds':1800,'frames':18000,'triangles':2000000,'poses':4096,'cpu_seconds':300,'pixels':134217728,'layers':2048}
_limits=ContextVar('creative_review_limits',default=FAST)
_progress=ContextVar('creative_review_progress',default=None)
_deadline=ContextVar('creative_review_deadline',default=None)
def limits():return _limits.get()
def progress(value,total,message):
    deadline=_deadline.get()
    if deadline and time.monotonic()>deadline:raise ValueError('Selected complete review exceeded CPU/time budget')
    callback=_progress.get()
    if callback:callback(value,total,message)
@contextmanager
def profile(name='fast',callback=None):
    if name not in {'fast','extended'}:raise ValueError('Unknown review profile')
    token=_limits.set(EXTENDED if name=='extended' else FAST);p=_progress.set(callback);d=_deadline.set(time.monotonic()+limits()['cpu_seconds'])
    try:yield
    finally:_deadline.reset(d);_progress.reset(p);_limits.reset(token)
