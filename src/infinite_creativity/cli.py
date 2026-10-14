import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
from .catalog import Catalog

def main():
    p=argparse.ArgumentParser(prog="infinite-creativity")
    p.add_argument("--db",default=os.environ.get("IC_CATALOG_DB","state/catalog.sqlite"))
    sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("sync")
    s.add_argument("--adapters",nargs="+")
    s.add_argument("--max-icon-sets",type=int,default=0)
    s.add_argument("--discovery-pages",type=int,default=2,choices=range(1,11))
    sub.add_parser("stats")
    q=sub.add_parser("search")
    q.add_argument("query",nargs="?",default="")
    q.add_argument("--kind",default="")
    q.add_argument("--style",default="")
    q.add_argument("--mode",default="usable",choices=["usable","reference","all"])
    q.add_argument("--limit",type=int,default=20)
    e=sub.add_parser("export")
    e.add_argument("--out",default="snapshots")
    a=p.parse_args()
    c=Catalog(a.db)
    try:
        if a.command == "sync":
            from .sync import sync
            report=sync(c,a.adapters,a.max_icon_sets,a.discovery_pages)
            if any(r["status"] != "ok" for r in report): raise SystemExit(2)
        elif a.command == "stats": print(json.dumps(c.stats(),ensure_ascii=False,indent=2))
        elif a.command == "search": print(json.dumps(c.search(a.query,kind=a.kind,style=a.style,mode=a.mode,limit=a.limit),ensure_ascii=False,indent=2))
        elif a.command == "export":
            from .locking import SyncLock
            export_lock=SyncLock(c.path)
            export_lock.__enter__()
            out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
            c.db.commit()
            c.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with gzip.open(out/"catalog.sqlite.gz","wb") as z: z.write(c.path.read_bytes())
            with gzip.open(out/"catalog.jsonl.gz","wt",encoding="utf-8") as z:
                for row in c.db.execute("SELECT * FROM assets WHERE active=1 ORDER BY id"):
                    z.write(json.dumps(c.decode(row),ensure_ascii=False)+"\n")
            manifest={"schema_version":1,"stats":c.stats(),"files":{f.name:{"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.glob("*.gz")}}
            (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(manifest,ensure_ascii=False))
    finally:
        c.close()
        if 'export_lock' in locals(): export_lock.__exit__()

if __name__ == "__main__": main()
