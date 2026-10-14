import json
from importlib.resources import files
from .adapters import polyhaven, ambientcg, iconify, github_tree, discover, discover_rotating, refresh_discovered, discover_partitions
from .catalog import now
from .network import Fetcher
from .policy import BLOCKED_URLS,BLOCKED_SOURCES
from .locking import SyncLock
from .asset_adapters import github_assets,fuel,khronos
from .kenney import kenney
from .audio_adapters import fsd50k
from .organization import organize
from .drive import quaternius
from .curation import curate
from .blender_demos import demos
from .inspiration import quaternius_studies
from .color_adapters import luts
from .codrops import codrops

def registry():
    return json.loads(files("infinite_creativity").joinpath("data/sources.json").read_text(encoding="utf-8"))

def sync(c, adapters=None, max_sets=0, discovery_pages=2, cache="state/http"):
    with SyncLock(c.path):
        return _sync_unlocked(c,adapters,max_sets,discovery_pages,cache)

def _sync_unlocked(c, adapters=None, max_sets=0, discovery_pages=2, cache="state/http"):
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
    selected = set(adapters or ["polyhaven","ambientcg","iconify","github-tree","github-assets","fuel","kenney-packs","khronos","references","fsd50k","quaternius","blender-demos","inspiration","luts","codrops"])
    for s in config["sources"]:
        c.source(s)
        previous=c.db.execute('SELECT status FROM sync_runs WHERE source=? ORDER BY id DESC LIMIT 1',(s['id'],)).fetchone()
        if s['adapter']=='reference' and previous and previous[0]=='failed':
            c.db.execute("INSERT INTO sync_runs(source,started,completed,status,count,error) VALUES (?,?,?,'disabled',0,'Automated adapter disabled; source retained as an unverified reference')",(s['id'],run,run))
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
    if 'github-assets' in selected:
        jobs.extend((s['id'],lambda s=s:github_assets(c,fetch,s,run)) for s in config['sources'] if s['adapter']=='github-assets')
    if 'fuel' in selected:
        jobs.append(('fuel-inventory',lambda:fuel(c,fetch,run)))
    if 'kenney-packs' in selected:
        jobs.append(('kenney-packs',lambda:kenney(c,fetch,run)))
    if 'khronos' in selected:
        jobs.append(('khronos-assets',lambda:khronos(c,fetch,run)))
    if 'fsd50k' in selected:jobs.append(('fsd50k',lambda:fsd50k(c,fetch,run)))
    if 'quaternius' in selected:jobs.append(('quaternius',lambda:quaternius(c,fetch,run)))
    if 'blender-demos' in selected:jobs.append(('blender-demos',lambda:demos(c,fetch,run)))
    if 'inspiration' in selected:jobs.append(('inspiration-quaternius',lambda:quaternius_studies(c,fetch,run)))
    if 'luts' in selected:jobs.append(('color-luts',lambda:luts(c,fetch,run)))
    if 'codrops' in selected:jobs.append(('codrops-inventory',lambda:codrops(c,fetch,run)))
    if "discovery" in selected:
        jobs.append(("github-discovery",lambda:discover(c,fetch,run,config["discovery_queries"],discovery_pages)))
    if 'discovery-rotate' in selected:
        jobs.append(('rotating-discovery',lambda:discover_rotating(c,fetch,run,config['discovery_queries'],discovery_pages)))
    if "refresh-discovered" in selected:
        jobs.append(("discovered-refresh",lambda:refresh_discovered(c,fetch,run)))
    if "discovery-more" in selected:
        jobs.append(("partitioned-discovery",lambda:discover_partitions(c,fetch,run,config['discovery_queries'])))
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
            import re
            error=str(e).replace(str(c.path.parent.resolve()),'[private-state]')
            error=re.sub(r'(?i)gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+','[redacted]',error)
            entry = {"source":sid,"status":"failed","count":0,"error":error[:2000]}
        c.db.execute("UPDATE sync_runs SET completed=?,status=?,count=?,error=? WHERE id=?",(now(),entry["status"],entry["count"],entry["error"],rid))
        c.db.commit()
        report.append(entry)
        print(json.dumps(entry,ensure_ascii=False), flush=True)
    organize(c)
    curate(c)
    return report
