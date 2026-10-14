"""Rotating, item-level Codrops code packs; external demo media is excluded."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from .asset_adapters import complete_tree
from .content import ContentCache
from .policy import acceptable

CODE = {'.html', '.css', '.scss', '.sass', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.vue', '.svelte', '.glsl', '.frag', '.vert'}
EXCLUDED = re.compile(r'(?:^|/)(?:node_modules|vendor|vendors|libs|lib|dist|build|\.git|\.github|tests?|__tests__)(?:/|$)|(?:\.min\.|(?:^|/)(?:jquery|three(?:\.module)?|gsap|TweenMax|TweenLite|modernizr|bootstrap|anime|imagesloaded|charming|smooth-scroll|dat\.gui)(?:[.-]))', re.I)

def code_entries(entries):
    return [e for e in entries if e['type']=='blob' and PurePosixPath(e['path']).suffix.lower() in CODE and not EXCLUDED.search(e['path']) and e.get('size',0)<=2*1024*1024]

def codrops(c, fetch, run, budget=24):
    c.db.execute('CREATE TABLE IF NOT EXISTS codrops_checks(repo TEXT PRIMARY KEY,checked TEXT)')
    repos=[]
    for page in range(1,21):
        rows=fetch.json(f'https://api.github.com/orgs/codrops/repos?per_page=100&type=public&page={page}')
        if not isinstance(rows,list):raise ValueError('Unexpected Codrops organization inventory')
        repos.extend(r for r in rows if not r.get('fork') and not r.get('private') and not r.get('archived') and acceptable(r['name']+' '+(r.get('description') or '')) and (r.get('license') or {}).get('spdx_id')=='MIT')
        if len(rows)<100:break
    else:raise ValueError('Codrops inventory pagination budget exhausted')
    checked=dict(c.db.execute('SELECT repo,checked FROM codrops_checks'))
    candidates=sorted(repos,key=lambda r:(checked.get(r['full_name'],''),-r.get('stargazers_count',0)))[:budget]
    cache=ContentCache(c.path.parent/'content');count=0;unsupported=[]
    for repo in candidates:
        name=repo['full_name'];branch=repo['default_branch']
        commit=fetch.json('https://api.github.com/repos/'+name+'/commits/'+quote(branch,safe=''))['sha']
        entries=complete_tree(fetch,name,commit)
        notice=next((e for e in entries if e['type']=='blob' and e['path'].upper() in {'LICENSE','LICENSE.TXT','LICENSE.MD'}),None)
        selected=code_entries(entries)
        if not notice or not selected:
            unsupported.append(name);c.db.execute('INSERT OR REPLACE INTO codrops_checks VALUES (?,?)',(name,run));continue
        raw=f'https://raw.githubusercontent.com/{name}/{commit}/'
        r=cache.fetch(raw+quote(notice['path'],safe='/'),'LICENSE.txt',256*1024)
        text=Path(r['path']).read_text(encoding='utf-8-sig',errors='replace')
        if 'permission is hereby granted, free of charge' not in text.lower() or 'the above copyright notice' not in text.lower():
            unsupported.append(name);c.db.execute('INSERT OR REPLACE INTO codrops_checks VALUES (?,?)',(name,run));continue
        title=repo['name'];canonical='https://github.com/'+name+'#creative-code-pack';sid='codrops-demo:'+title
        selected.sort(key=lambda e:(e['path'].lower()!='index.html',not e['path'].lower().endswith('.html'),e['path']))
        description=repo.get('description') or title
        source={'id':sid,'name':'Codrops / '+title,'url':'https://github.com/'+name,'repo':name,'adapter':'codrops','status':'first-party-code-pack-only','media':['motion','template','shader']}
        c.source(source)
        kind='template' if re.search(r'template|layout|portfolio|website|landing',title+' '+description,re.I) else 'motion'
        first=selected[0];licurl='https://github.com/'+name+'/blob/'+commit+'/'+quote(notice['path'],safe='/')
        revision=hashlib.sha256(''.join(e['sha'] for e in selected+[notice]).encode()).hexdigest()
        author='; '.join(re.findall(r'(?im)^.*copyright.*$',text))[:500] or 'Codrops (repository publisher; read original notice)'
        if c.upsert(sid,name,title,kind,canonical,license='MIT',license_url=licurl,author=author,tags=['Codrops','creative-code',title,description],platforms=['web'],formats=sorted({PurePosixPath(e['path']).suffix.lstrip('.') for e in selected}),access_url=raw+quote(first['path'],safe='/'),revision=revision,run=run):
            aid=hashlib.sha256(canonical.encode()).hexdigest()[:24]
            files=[{'url':raw+quote(e['path'],safe='/'),'filename':PurePosixPath(e['path']).name,'relative_path':e['path'],'sha':e['sha'],'bytes':e.get('size'),'role':'main' if e==first else 'license' if e==notice else 'dependency'} for e in selected+[notice]]
            c.set_details(aid,{'description':description,'pack_name':title,'pack_scope':name,'files':files,'features':{'publisher':'Codrops','code_files':len(selected),'complete_code_scope':'Selected unminified code and shaders, excluding vendor/lib/build paths. Media, fonts and third-party libraries are not implied to share MIT rights.','external_requirements':'Read source imports and README; demo images, fonts, packages and hosted services require their own rights and setup.','upstream_readme':raw+'README.md'},'commit':commit})
            count+=1
        c.reconcile(sid,run)
        c.db.execute('INSERT OR REPLACE INTO codrops_checks VALUES (?,?)',(name,run));c.db.commit()
        print(json.dumps({'progress':'codrops','pack':title,'code_files':len(selected),'indexed':count}),flush=True)
    total=c.db.execute("SELECT count(*) FROM assets WHERE active=1 AND source LIKE 'codrops-demo:%'").fetchone()[0]
    done={r[0] for r in c.db.execute('SELECT repo FROM codrops_checks')}
    checked_total=sum(r['full_name'] in done for r in repos)
    c.source({'id':'codrops','name':'Codrops','url':'https://tympanus.net/codrops/hub/','adapter':'codrops','status':'rotating-first-party-code-packs','coverage':{'eligible_public_mit_repositories':len(repos),'checked_eligible_repositories':checked_total,'checked_this_run':len(candidates),'indexed_code_packs':total,'unsupported_this_run':unsupported,'whole_provider_indexed':False,'note':'Selected first-party code inventories, not all Codrops posts or third-party media.'}})
    return count
