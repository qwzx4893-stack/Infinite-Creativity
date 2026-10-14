"""One index writer per database; advisory lock is released on process exit."""
import os
from pathlib import Path

class SyncLock:
    def __init__(self,path): self.path=Path(str(path)+'.sync.lock')
    def __enter__(self):
        self.handle=self.path.open('a+b')
        self.handle.seek(0,2)
        if self.handle.tell()==0:
            self.handle.write(b'0'); self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError('Another catalog sync is active for this database') from None
        return self
    def __exit__(self,*args):
        self.handle.close()
