"""Fresh repository federation across media/themes, with scoped rights per item."""
import json,re
from urllib.parse import quote
from .policy import acceptable,review_terms


def github_current(http,s,f,after,limit,key=None):
    from .live_providers import github
    if key:
        repo,path=key.split('|',1)
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository locator')
        config={**s,'repo':repo,'adapter':'github-assets'}
        a=github(http,config,{'mode':'all'},'',1,key=path);a['key']=repo+'|'+a['key'];a['repo']=repo
        a['pack']=repo+'|'+(a.get('pack') or '.')
        return a
    state=json.loads(after) if after else {'page':1,'repo':0,'member':''}
    pack=f.get('_pack_key','');scoped_repo,_,scoped_pack=pack.partition('|')
    if pack:
        repos=[{'full_name':scoped_repo}];index=0
    else:
        query=(f.get('query') or f.get('style') or s.get('search','game assets'))+' license:cc0-1.0 archived:false fork:false'
        data=http.json('https://api.github.com/search/repositories?q='+quote(query)+f'&per_page=10&page={state["page"]}')
        repos=data.get('items',[]);index=state['repo']
    rows=[];errors=[];member=state['member'];next_position=None
    # One query exposes real original members, not repository directory cards.
    # Two repository windows per call keep network budgets bounded.
    for index in range(index,min(len(repos),index+2)):
        repo=repos[index]['full_name'];config={**s,'repo':repo,'adapter':'github-assets'}
        text=repo+' '+(repos[index].get('description') or '')
        if not acceptable(text) or review_terms(text):member='';continue
        try:
            view=github(http,config,{**f,**({'_pack_key':scoped_pack} if pack else {})},member,limit-len(rows))
            for a in view['items']:
                a['key']=repo+'|'+a['key'];a['repo']=repo;a['pack']=repo+'|'+(a.get('pack') or '.');rows.append(a)
            if view.get('next') is not None:next_position={'page':state['page'],'repo':index,'member':view['next']};break
        except ValueError as e:errors.append({'repository':repo,'reason':str(e)[:180]})
        member=''
        if len(rows)>=limit:
            next_position={'page':state['page'],'repo':index+1,'member':''};break
    if next_position is None:
        if index+1<len(repos):next_position={'page':state['page'],'repo':index+1,'member':''}
        elif not pack and len(repos)==10 and state['page']<100:next_position={'page':state['page']+1,'repo':0,'member':''}
    return {'items':rows,'next':json.dumps(next_position) if next_position else None,'total':None,
            'scope':'Current CC0 repository search followed by individually scoped media members; no saved repository results','repository_errors':errors}
