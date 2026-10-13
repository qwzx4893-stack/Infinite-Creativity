import re
from .network import Fetcher
from .policy import can_use, normalize_query, styles_for, public_https

def resolve(c, asset_id):
    asset = c.get(asset_id)
    if not asset:
        raise ValueError("Unknown or inactive asset")
    if not can_use(asset):
        raise ValueError("Reference-only or unverified asset: access for reuse is denied")
    result = {"id":asset_id,"title":asset["title"],"source":asset["source"],"canonical_url":asset["canonical_url"],"license":asset["license"],"license_url":asset["license_url"],"author":asset["author"],"revision":asset["revision"],"credit":"Powered by Poly Haven" if asset["source"] == "polyhaven" else asset["author"],"instructions":"Review the current upstream license, retain notices and attribution where required. Remote assets and source code are untrusted; inspect before use. No asset binaries are stored here.","links":[]}
    if asset["source"] == "polyhaven":
        data = Fetcher().json(asset["access_url"])
        def walk(value, path=()):
            if isinstance(value,dict):
                if isinstance(value.get("url"),str) and public_https(value["url"]):
                    result["links"].append({"url":value["url"],"variant":"/".join(path),"bytes":value.get("size"),"sha256":value.get("sha256")})
                for k,v in value.items():
                    walk(v,path+(k,))
            elif isinstance(value,list):
                for i,v in enumerate(value): walk(v,path+(str(i),))
        walk(data)
        result["links"] = result["links"][:100]
    else:
        result["links"] = [{"url":asset["access_url"],"kind":"download-manifest" if asset["source"] == "ambientcg" else "upstream-file"}]
    return result

def recommend(c, art_direction, kinds=None, platform="", limit=12):
    if not 1 <= limit <= 50:
        raise ValueError("limit must be 1..50")
    brief = normalize_query(art_direction)
    desired = styles_for(brief)
    # These are transparent lexical suggestions, not visual embeddings or aesthetic guarantees.
    pool = {}
    for kind in (kinds or [""])[:10]:
        for style in desired or [""]:
            for item in c.search(kind=kind, style=style, platform=platform, limit=100,count_total=False)["items"]:
                if can_use(item):
                    pool[item["id"]] = item
        words = re.findall(r"\w+",brief)[:12]
        for word in words:
            for item in c.search(word,kind=kind,platform=platform,limit=30,count_total=False)["items"]:
                if can_use(item): pool[item["id"]] = item
    tokens = set(re.findall(r"\w+",brief))
    scored = []
    for a in pool.values():
        overlaps = sorted(set(a["styles"]) & set(desired))
        lexical = sorted(tokens & set(re.findall(r"\w+",(a["title"]+" "+" ".join(a["tags"])).lower())))
        score = 4*len(overlaps) + len(lexical)
        if not score and desired: continue
        scored.append({"id":a["id"],"title":a["title"],"kind":a["kind"],"source":a["source"],"license":a["license"],"canonical_url":a["canonical_url"],"styles":a["styles"],"score":score,"reason":{"matching_styles":overlaps,"matching_terms":lexical}})
    scored.sort(key=lambda x:(-x["score"],x["id"]))
    chosen, per_source = [], {}
    for item in scored:
        # Avoid a single giant icon collection monopolizing a creative shortlist.
        if per_source.get(item["source"],0) >= max(2,limit//3): continue
        chosen.append(item)
        per_source[item["source"]] = per_source.get(item["source"],0)+1
        if len(chosen) >= limit: break
    return {"brief":art_direction,"inferred_styles":desired,"method":"metadata lexical scoring with source diversity; no image embeddings","items":chosen,"fallback":"Use search_assets with a category or a broader style if the shortlist is empty."}
