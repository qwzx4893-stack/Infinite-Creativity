"""Private sessions and collections live outside exported catalog data."""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

class Runtime:
    def __init__(self,folder):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.folder/'runtime.sqlite',timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,filters TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,name TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS collection_items(collection_id TEXT,asset_id TEXT,PRIMARY KEY(collection_id,asset_id));''')
        secret_path=self.folder/'cursor.key'
        if not secret_path.exists():
            try:
                with secret_path.open('xb') as f: f.write(secrets.token_bytes(32))
            except FileExistsError: pass
        self.secret=secret_path.read_bytes()
    def close(self): self.db.close()
    def session(self,filters):
        sid=uuid.uuid4().hex
        self.db.execute('INSERT INTO sessions VALUES (?,?,?)',(sid,json.dumps(filters),time.time())); self.db.commit()
        return sid
    def filters(self,sid):
        row=self.db.execute('SELECT filters,created FROM sessions WHERE id=?',(sid,)).fetchone()
        if not row or time.time()-row['created']>86400: raise ValueError('Unknown or expired library session')
        return json.loads(row['filters'])
    def cursor(self,sid,position):
        payload=json.dumps({'session':sid,'position':position},sort_keys=True,separators=(',',':')).encode()
        signature=hmac.new(self.secret,payload,hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature+payload).decode().rstrip('=')
    def position(self,sid,token):
        try:
            if len(token)>4096: raise ValueError()
            raw=base64.urlsafe_b64decode(token+'='*(-len(token)%4))
            signature,payload=raw[:32],raw[32:]
            if not hmac.compare_digest(signature,hmac.new(self.secret,payload,hashlib.sha256).digest()): raise ValueError()
            data=json.loads(payload)
            if data['session']!=sid: raise ValueError()
            return data['position']
        except (ValueError,KeyError,TypeError): raise ValueError('Invalid library cursor') from None
    def collection(self,name):
        cid=uuid.uuid4().hex
        self.db.execute('INSERT INTO collections VALUES (?,?,?)',(cid,name[:200],time.time())); self.db.commit(); return cid
    def add(self,cid,ids):
        if not self.db.execute('SELECT 1 FROM collections WHERE id=?',(cid,)).fetchone(): raise ValueError('Unknown collection')
        self.db.executemany('INSERT OR IGNORE INTO collection_items VALUES (?,?)',[(cid,aid) for aid in ids]); self.db.commit()
    def items(self,cid): return [r[0] for r in self.db.execute('SELECT asset_id FROM collection_items WHERE collection_id=? ORDER BY asset_id',(cid,))]
