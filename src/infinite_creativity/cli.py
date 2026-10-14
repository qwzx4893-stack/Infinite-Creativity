import argparse
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path
from .catalog import Catalog

def main():
    p=argparse.ArgumentParser(prog="infinite-creativity")
    p.add_argument("--db",default=None)
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
    q.add_argument('--source',default='')
    q.add_argument('--section',default='')
    q.add_argument("--mode",default="usable",choices=["usable","reference","all"])
    q.add_argument("--limit",type=int,default=20)
    e=sub.add_parser("export")
    e.add_argument("--out",default="snapshots")
    sub.add_parser('curate')
    sub.add_parser('prepare-vision')
    v=sub.add_parser('screen-vision');v.add_argument('--limit',type=int,default=500);v.add_argument('--source',default='')
    v=sub.add_parser('apply-reviews');v.add_argument('file')
    a=p.parse_args()
    if a.db is None and os.environ.get('IC_MODE')!='legacy-indexed':
        from .live import LiveLibrary
        if a.command=='stats':print(json.dumps(LiveLibrary().overview(),ensure_ascii=False,indent=2));return
        if a.command=='search':print(json.dumps(LiveLibrary().open(query=a.query,kind=a.kind,style=a.style,mode=a.mode,source=a.source,section=a.section,limit=a.limit),ensure_ascii=False,indent=2));return
        raise SystemExit('Snapshot/index commands are retired from the default live library. Explicit --db is required for historical offline maintenance.')
    c=Catalog(a.db or os.environ.get('IC_CATALOG_DB','state/catalog.sqlite'))
    try:
        if a.command == "sync":
            from .sync import sync
            report=sync(c,a.adapters,a.max_icon_sets,a.discovery_pages)
            if any(r["status"] != "ok" for r in report): raise SystemExit(2)
        elif a.command == "stats": print(json.dumps(c.stats(),ensure_ascii=False,indent=2))
        elif a.command in {'curate','prepare-vision','screen-vision','apply-reviews'}:
            from .locking import SyncLock
            with SyncLock(c.path):
                if a.command=='prepare-vision':
                    from .vision import prepare
                    prepare(c.path.parent/'models/nsfw-five-class');result={'model':'Prepared pinned local ONNX classifier'}
                elif a.command=='curate':
                    from .curation import curate
                    result=curate(c)
                elif a.command=='apply-reviews':
                    from .curation import apply_reviews
                    result=apply_reviews(c,json.loads(Path(a.file).read_text(encoding='utf-8')))
                else:
                    from .vision import screen_catalog
                    result=screen_catalog(c,a.limit,a.source)
                stamp=__import__('infinite_creativity.catalog',fromlist=['now']).now()
                c.db.execute('INSERT INTO sync_runs(source,started,completed,status,count,error) VALUES (?,?,?,?,?,?)',(a.command,stamp,stamp,'ok',result.get('checked',0),''));c.db.commit()
                print(json.dumps(result,ensure_ascii=False))
        elif a.command == "search": print(json.dumps(c.search(a.query,kind=a.kind,style=a.style,mode=a.mode,limit=a.limit),ensure_ascii=False,indent=2))
        elif a.command == "export":
            from .locking import SyncLock
            export_lock=SyncLock(c.path)
            export_lock.__enter__()
            out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
            c.db.commit()
            c.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with c.path.open('rb') as src, gzip.open(out/"catalog.sqlite.gz","wb",compresslevel=1) as z:
                shutil.copyfileobj(src,z,1024*1024)
            print('SQLite snapshot exported; exporting record manifests',flush=True)
            with gzip.open(out/"catalog.jsonl.gz","wt",encoding="utf-8",compresslevel=1) as z:
                for row in c.db.execute("SELECT a.*,d.data AS details_json,s.section_id,s.pack_id,r.quality_state,r.safety_state AS safety_review,r.duplicate_of,r.data curation_json FROM assets a LEFT JOIN asset_details d ON a.id=d.asset_id LEFT JOIN asset_sections s ON s.asset_id=a.id LEFT JOIN curation r ON r.asset_id=a.id WHERE a.active=1 ORDER BY a.id"):
                    item=c.decode(row)
                    item['details']=json.loads(item.pop('details_json')) if item.get('details_json') else {}
                    item.pop('details_json',None)
                    item['curation_evidence']=json.loads(item.pop('curation_json') or '{}')
                    z.write(json.dumps(item,ensure_ascii=False)+"\n")
            for table,filename in [('containers','containers.jsonl.gz'),('packs','packs.jsonl.gz')]:
                with gzip.open(out/filename,'wt',encoding='utf-8',compresslevel=1) as z:
                    for row in c.db.execute('SELECT * FROM '+table+' ORDER BY id'):z.write(json.dumps(dict(row),ensure_ascii=False)+'\n')
            manifest={"schema_version":3,"server_version":"0.3.0","content":"Metadata, hierarchy, public containers, pack and curation evidence only; private sessions, collections, models and content cache excluded.","stats":c.stats(),"files":{f.name:{"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.glob("*.gz")}}
            (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(manifest,ensure_ascii=False))
    finally:
        c.close()
        if 'export_lock' in locals(): export_lock.__exit__()

if __name__ == "__main__": main()
