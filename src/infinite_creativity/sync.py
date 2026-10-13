import json
from importlib.resources import files
from .adapters import polyhaven, ambientcg, iconify, github_tree, discover, refresh_discovered
from .catalog import now
from .network import Fetcher
from .policy import BLOCKED_URLS,BLOCKED_SOURCES

def registry():
    return json.loads(files("infinite_creativity").joinpath("data/sources.json").read_text(encoding="utf-8"))

def sync(c, adapters=None, max_sets=0, discovery_pages=2, cache="state/http"):
    config = registry()
    # A previous process may have exited before its source completed.
    c.db.execute("UPDATE sync_runs SET status='interrupted',completed=?,error='Process ended before completion; previous records retained' WHERE status='running'",(now(),))
    for url in BLOCKED_URLS:
        c.db.execute("UPDATE assets SET active=0 WHERE canonical_url=?",(url,))
    for sid in BLOCKED_SOURCES:
        c.db.execute("UPDATE assets SET active=0 WHERE source=?",(sid,))
    fetch = Fetcher(cache)
    report = []
    run = now()
    selected = set(adapters or ["polyhaven","ambientcg","iconify","github-tree","references"])
    for s in config["sources"]:
        c.source(s)
    c.db.commit()
    jobs = []
    if "references" in selected:
        def refs():
            n = 0
            for s in config["sources"]:
                if s["adapter"] == "reference":
                    n += c.upsert(s["id"], s["id"], s["name"], "source-reference", s["url"], tags=s.get("tags",[]), mode="reference", safety="review-required", run=run)
            return n
        jobs.append(("references",refs))
    if "polyhaven" in selected:
        jobs.append(("polyhaven",lambda:polyhaven(c,fetch,run)))
    if "ambientcg" in selected:
        jobs.append(("ambientcg",lambda:ambientcg(c,fetch,run)))
    if "iconify" in selected:
        jobs.append(("iconify",lambda:iconify(c,fetch,run,max_sets)))
    if "github-tree" in selected:
        jobs.extend((s["id"], lambda s=s:github_tree(c,fetch,s,run)) for s in config["sources"] if s["adapter"] == "github-tree")
    if "discovery" in selected:
        jobs.append(("github-discovery",lambda:discover(c,fetch,run,config["discovery_queries"],discovery_pages)))
    if "refresh-discovered" in selected:
        jobs.append(("discovered-refresh",lambda:refresh_discovered(c,fetch,run)))
    for sid, job in jobs:
        started = now()
        cur = c.db.execute("INSERT INTO sync_runs(source,started,status,count,error) VALUES (?,?, 'running',0,'')", (sid,started))
        rid = cur.lastrowid
        c.db.commit()
        try:
            count = job()
            entry = {"source":sid,"status":"ok","count":count,"error":""}
        except Exception as e:
            # Preserve prior snapshots and partial valid updates. No stale reconciliation on failure.
            entry = {"source":sid,"status":"failed","count":0,"error":str(e)[:2000]}
        c.db.execute("UPDATE sync_runs SET completed=?,status=?,count=?,error=? WHERE id=?",(now(),entry["status"],entry["count"],entry["error"],rid))
        c.db.commit()
        report.append(entry)
        print(json.dumps(entry,ensure_ascii=False), flush=True)
    return report
