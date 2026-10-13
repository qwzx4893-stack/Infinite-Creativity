"""Metadata only. No scraping, executable imports, or upstream binaries."""
import json
import re
from urllib.parse import quote
from .policy import LICENSES, acceptable
from .catalog import now

def polyhaven(c, fetch, run):
    data = fetch.json("https://api.polyhaven.com/assets")
    count = 0
    for key, a in data.items():
        count += c.upsert("polyhaven", key, a.get("name", key), {0:"hdri",1:"texture",2:"model-3d"}.get(a.get("type"), "asset-3d"), "https://polyhaven.com/a/" + quote(key), license="CC0-1.0", license_url="https://polyhaven.com/license", author=", ".join(a.get("authors", {})), tags=a.get("tags", []) + a.get("categories", []) + [a.get("description", "")[:600]], formats=["hdr", "exr"] if a.get("type") == 0 else ["blend", "gltf"] if a.get("type") == 2 else ["png", "jpg", "exr"], platforms=["web","desktop","mobile","game"], access_url="https://api.polyhaven.com/files/"+quote(key), revision=a.get("files_hash", ""), run=run)
    c.reconcile("polyhaven", run)
    return count

def ambientcg(c, fetch, run):
    offset, count = 0, 0
    while True:
        data = fetch.json(f"https://ambientcg.com/api/v2/full_json?limit=250&offset={offset}&include=tagData&sort=Alphabet")
        rows = data.get("foundAssets", [])
        for a in rows:
            key = a["assetId"]
            count += c.upsert("ambientcg", key, a.get("displayName", key), {"3DModel":"model-3d", "HDRI":"hdri", "Material":"material", "PlainTexture":"texture", "Decal":"decal", "Atlas":"atlas", "Substance":"material", "Terrain":"terrain", "Brush":"brush"}.get(a.get("dataType"), "texture"), "https://ambientcg.com/a/"+quote(key), license="CC0-1.0", license_url="https://docs.ambientcg.com/license/", author="ambientCG", tags=a.get("tags", []) + [a.get("creationMethod", "")], platforms=["web","desktop","mobile","game"], access_url="https://ambientcg.com/api/v2/full_json?id="+quote(key)+"&include=downloadData", revision=a.get("releaseDate", ""), run=run)
        if len(rows) < 250:
            break
        offset += 250
        if offset > 1000000:
            raise RuntimeError("ambientCG pagination exceeded budget")
    c.reconcile("ambientcg", run)
    return count

def iconify(c, fetch, run, max_sets=0):
    # Use the project's official bulk distribution instead of hundreds of listing API calls.
    collections = fetch.json("https://raw.githubusercontent.com/iconify/icon-sets/master/collections.json")
    count, errors = 0, []
    for index, (prefix, info) in enumerate(collections.items()):
        if max_sets and index >= max_sets:
            break
        lic = info.get("license", {})
        spdx = lic.get("spdx", "unknown")
        # Unverified or restrictive collections never enter the reusable asset pool.
        if spdx not in LICENSES or not lic.get("url"):
            continue
        sid = "iconify:" + prefix
        c.source({"id":sid,"name":info.get("name",prefix),"url":"https://icon-sets.iconify.design/"+prefix+"/", "adapter":"iconify", "license":spdx,"license_url":lic.get("url"),"access":"free","upstream_author":info.get("author",{})})
        try:
            listing = fetch.json("https://raw.githubusercontent.com/iconify/icon-sets/master/json/"+quote(prefix)+".json")
            live_license=listing.get("info",{}).get("license",{})
            if live_license.get("spdx") != spdx:
                raise RuntimeError("Collection license changed during sync; defer for review")
            names = {name for name,icon in listing.get("icons",{}).items() if not icon.get("hidden")}
            categories = {}
            for category, items in listing.get("categories", {}).items():
                for name in items:
                    names.add(name)
                    categories.setdefault(name, []).append(category)
            # Hidden/alias icons are not counted as independent creative originals.
            for name in sorted(names):
                styles = ["colorful"] if info.get("palette") else ["monochrome"]
                count += c.upsert(sid, name, name.replace("-", " "), "icon", f"https://icon-sets.iconify.design/{prefix}/{name}/", license=spdx, license_url=lic["url"], author=info.get("author",{}).get("name",""), tags=[prefix, info.get("name",prefix)] + styles + categories.get(name,[]), platforms=["web","desktop","mobile"], formats=["svg"], access_url=f"https://api.iconify.design/{prefix}/{name}.svg", revision=str(info.get("version", "")), run=run)
            c.reconcile(sid, run)
            c.db.commit()
            print(json.dumps({"progress":"iconify","collection":prefix,"indexed_so_far":count}),flush=True)
        except Exception as e:
            if "HTTP 429" in str(e) or "HTTP 403" in str(e):
                raise RuntimeError(f"Collection sync deferred after {count} records: {e}") from None
            errors.append({"source": sid, "error": type(e).__name__ + ": " + str(e)[:160]})
    if errors:
        raise RuntimeError(json.dumps({"partial_count":count, "errors":errors}))
    return count

def github_tree(c, fetch, source, run):
    repo = source["repo"]
    meta = fetch.json("https://api.github.com/repos/"+repo)
    branch = meta["default_branch"]
    tree = fetch.json(f"https://api.github.com/repos/{repo}/git/trees/{quote(branch, safe='')}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Truncated GitHub tree: completeness not claimed; implement subtree traversal")
    spdx = (meta.get("license") or {}).get("spdx_id", "unknown")
    license_path = next((x["path"] for x in tree.get("tree",[]) if x["path"].upper() in {"LICENSE", "LICENSE.MD", "LICENSE.TXT", "COPYING"}), "LICENSE")
    license_url = f"https://github.com/{repo}/blob/{quote(branch)}/{license_path}"
    count = 0
    for file in tree.get("tree", []):
        path = file["path"]
        if file["type"] != "blob" or not re.search(source.get("path_pattern", r"\.(tsx|vue|svelte|css|html|svg|glb|gltf|blend)$"), path):
            continue
        if re.search(r"(^|/)(node_modules|vendor|\.github|tests?|__tests__|dist)(/|$)", path):
            continue
        kind, lic, lu = source.get("kind", "ui-component"), spdx, license_url
        if repo == "google/fonts":
            if not path.endswith("/METADATA.pb") or path.split('/')[0] not in {"ofl","apache","ufl"}:
                continue
            kind = "font"
            lic = {"ofl":"OFL-1.1", "apache":"Apache-2.0", "ufl":"LicenseRef-UFL"}[path.split('/')[0]]
            lu = f"https://github.com/{repo}/blob/{quote(branch)}/"+path.rsplit('/',1)[0]+("/OFL.txt" if lic == "OFL-1.1" else "/LICENSE.txt")
        url = f"https://github.com/{repo}/blob/{quote(branch)}/{quote(path, safe='/')}"
        # Catalog components from explicitly reviewed code collections; general discoveries remain references.
        mode = "usable" if source.get("license_scope_reviewed") and lic in LICENSES else "reference"
        count += c.upsert(source["id"], path, path.rsplit('/',1)[0].split('/')[-1] if kind == "font" else path.rsplit('/',1)[-1], kind, url, license=lic, license_url=lu, author=repo.split('/')[0], tags=source.get("tags",[]) + path.split('/'), platforms=source.get("platforms",["web"]), formats=[path.rsplit('.',1)[-1]], access_url=f"https://raw.githubusercontent.com/{repo}/{quote(branch)}/{quote(path, safe='/')}", revision=file["sha"], mode=mode, run=run)
    c.reconcile(source["id"], run)
    return count

def discover(c, fetch, run, queries, pages=2):
    count = 0
    for query in queries:
        for page in range(1, min(pages,10)+1):
            result = fetch.json("https://api.github.com/search/repositories?q="+quote(query+" archived:false fork:false")+f"&per_page=100&page={page}&sort=stars")
            if result.get("incomplete_results"):
                raise RuntimeError("GitHub search returned incomplete results; narrow the query")
            for repo in result.get("items",[]):
                text = repo["full_name"] + " " + (repo.get("description") or "") + " " + " ".join(repo.get("topics",[]))
                if not acceptable(text):
                    continue
                sid = "github:"+repo["full_name"]
                c.source({"id":sid,"name":repo["full_name"],"url":repo["html_url"],"repo":repo["full_name"],"adapter":"discovery", "status":"license-and-content-review-required", "license":(repo.get("license") or {}).get("spdx_id","unknown"),"discovery_query":query,"checked_at":now()})
                count += c.upsert(sid, repo["full_name"], repo["name"], "repository", repo["html_url"], tags=repo.get("topics",[]) + [(repo.get("description") or "")[:500]], platforms=["web","desktop","mobile"], license=(repo.get("license") or {}).get("spdx_id","unknown"), license_url=repo["html_url"]+"/blob/"+quote(repo["default_branch"])+"/LICENSE", author=repo["owner"]["login"], revision=repo["pushed_at"], mode="reference", safety="metadata-screened", run=run)
            c.db.commit()
            if len(result.get("items", [])) < 100:
                break
    return count

def refresh_discovered(c, fetch, run, budget=100):
    """Rotate through known sources by oldest observation; do not reclassify references as usable."""
    sources=[json.loads(r[0]) for r in c.db.execute("SELECT data FROM sources")]
    candidates=sorted((s for s in sources if s.get("adapter")=="discovery"),key=lambda s:s.get("checked_at",""))[:budget]
    count=0
    errors=[]
    for s in candidates:
        try:
            repo=fetch.json("https://api.github.com/repos/"+s["repo"])
            s["checked_at"]=now()
            s["license"]=(repo.get("license") or {}).get("spdx_id","unknown")
            c.source(s)
            text=repo["full_name"]+" "+(repo.get("description") or "")+" "+" ".join(repo.get("topics",[]))
            if not acceptable(text) or repo.get("archived"):
                c.db.execute("UPDATE assets SET active=0 WHERE source=?",(s["id"],))
            else:
                count+=c.upsert(s["id"],repo["full_name"],repo["name"],"repository",repo["html_url"],tags=repo.get("topics",[])+[(repo.get("description") or "")[:500]],platforms=["web","desktop","mobile"],license=s["license"],license_url=repo["html_url"]+"/blob/"+quote(repo["default_branch"])+"/LICENSE",author=repo["owner"]["login"],revision=repo["pushed_at"],mode="reference",run=run)
            c.db.commit()
        except RuntimeError as e:
            if "HTTP 404" in str(e) or "HTTP 451" in str(e):
                c.db.execute("UPDATE assets SET active=0 WHERE source=?",(s["id"],))
                s.update(status="unavailable",checked_at=now()); c.source(s); c.db.commit()
            else: errors.append(s["id"]+": "+str(e))
    if errors: raise RuntimeError("; ".join(errors)[:2000])
    return count
