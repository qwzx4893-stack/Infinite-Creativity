import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from .network import Fetcher
from .policy import can_use, normalize_query, styles_for, public_https

def resolve(c, asset_id):
    asset = c.get(asset_id)
    if not asset:
        raise ValueError("Unknown or inactive asset")
    if not can_use(asset):
        raise ValueError("Reference-only or unverified asset: access for reuse is denied")
    result = {"id":asset_id,"title":asset["title"],"source":asset["source"],"canonical_url":asset["canonical_url"],"license":asset["license"],"license_url":asset["license_url"],"author":asset["author"],"revision":asset["revision"],"credit":"Powered by Poly Haven" if asset["source"] == "polyhaven" else asset["author"],"instructions":"Review the current upstream license, retain notices and attribution where required. Remote assets and source code are untrusted; inspect before use. No asset binaries are stored here.","links":[]}
    details=c.details(asset_id)
    if any(f.get('container_id') for f in details.get('files',[])):
        result['resource_uri']='creativity://asset/'+asset_id
        result['internal_actions']=['asset_files','fetch_asset','read_asset_file','preview_audio_asset']
        result['instructions']='Retrieve the individually licensed archive member inside MCP. The dataset archive contains other recordings with different licenses; its raw archive URL is not a reusable clip link.'
        return result
    if asset["source"] == "polyhaven":
        data = Fetcher(c.path.parent/'http').json(asset["access_url"])
        def walk(value, path=(), bundle='', relative=''):
            if isinstance(value,dict):
                if isinstance(value.get("url"),str) and public_https(value["url"]):
                    key=bundle or '/'.join(path)
                    filename=PurePosixPath(urlsplit(value['url']).path).name
                    result["links"].append({"url":value["url"],"filename":filename,"relative_path":relative or filename,"variant":"/".join(path),"bundle_key":key,"role":"dependency" if bundle else "variant","bytes":value.get("size"),"sha256":value.get("sha256"),"md5":value.get('md5')})
                    for name,dep in value.get('include',{}).items(): walk(dep,path+('include',name),key,name)
                for k,v in value.items():
                    if k!='include': walk(v,path+(k,),bundle,relative)
            elif isinstance(value,list):
                for i,v in enumerate(value): walk(v,path+(str(i),),bundle,relative)
        walk(data)
        if len(result['links'])>2000: raise ValueError('Provider file manifest exceeded budget')
    elif asset['source']=='google-fonts' and asset['kind']=='font':
        family=asset['upstream_id'].rsplit('/',1)[0]
        data=Fetcher(c.path.parent/'http').json('https://api.github.com/repos/google/fonts/contents/'+family)
        result['links']=[{'url':entry['download_url'],'filename':entry['name'],'relative_path':family+'/'+entry['name'],'bytes':entry.get('size'),'sha':entry.get('sha'),'role':'license' if entry['name'].lower().endswith('.txt') else 'variant'} for entry in data if entry.get('download_url') and entry['name'].lower().endswith(('.ttf','.otf','.woff','.woff2','.txt'))][:100]
        first=next((f for f in result['links'] if f['role']=='variant'),None)
        if first: first['role']='main'
        result['links'].sort(key=lambda f:f['role']!='main')
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
    # Sample each medium independently: the largest icon inventory must not
    # determine the candidate pool for an otherwise unrestricted creative brief.
    requested = list(dict.fromkeys(kinds or []))
    sampled = requested or ["model-3d", "animation-3d", "scene-3d", "material", "texture", "hdri", "audio", "sprite", "animation-2d", "illustration", "ui-asset", "ui-component", "template", "motion", "shader", "lut", "font", "video", "icon"]
    for kind in sampled[:24]:
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
    chosen, per_source, per_kind = [], {}, {}
    for item in scored:
        # Avoid a single giant icon collection monopolizing a creative shortlist.
        if per_source.get(item["source"],0) >= max(2,limit//3): continue
        if not requested and per_kind.get(item["kind"],0) >= max(1,limit//4): continue
        chosen.append(item)
        per_source[item["source"]] = per_source.get(item["source"],0)+1
        per_kind[item["kind"]] = per_kind.get(item["kind"],0)+1
        if len(chosen) >= limit: break
    return {"brief":art_direction,"inferred_styles":desired,"method":"metadata lexical scoring with per-medium sampling and source/medium diversity; no image embeddings","sampled_kinds":sampled[:24],"items":[{**i,"resource_uri":"creativity://asset/"+i["id"],"actions":["get_library_item","asset_files"]} for i in chosen],"fallback":"Use library_sections and library_packs, or provide explicit kinds to focus the shortlist."}
