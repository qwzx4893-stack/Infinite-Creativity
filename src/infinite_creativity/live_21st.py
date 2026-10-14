"""Official 21st MCP read federation; no marketplace scraper or AI generation."""
import asyncio,json,os,re
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def read_remote(name, query='', key='', page=1, limit=20):
    token=os.environ.get('API_KEY_21ST')
    if not token:raise ValueError('Official API_KEY_21ST required; get an account-authorized key from 21st.dev/mcp')
    async with httpx.AsyncClient(headers={'x-api-key':token},timeout=12,follow_redirects=False) as client:
        async with streamable_http_client('https://21st.dev/api/mcp',http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize();tools=(await session.list_tools()).tools
                tool=next((t for t in tools if t.name==name),None)
                if not tool or name!='search':raise ValueError('Official metadata search capability unavailable for this account')
                properties=tool.inputSchema.get('properties',{});args={}
                aliases=(('query',query),('q',query),('search',query),('keyword',query)) if name=='search' else (('component_id',key),('componentId',key),('id',key),('slug',key))
                for k,v in aliases:
                    if k in properties:args[k]=v;break
                if not args:raise ValueError('Unsupported current official tool schema; no guessed generation or protected-content fallback')
                if 'page' in properties:args['page']=page
                if 'limit' in properties:args['limit']=limit
                for option in ('include_code','includeCode','include_source'):
                    if option in properties:args[option]=False
                result=await session.call_tool(name,args)
                if result.isError:raise ValueError('Official 21st read operation rejected by account permissions')
                data=result.structuredContent
                if data is None:
                    text=''.join(b.text for b in result.content if b.type=='text')
                    if len(text)>2*1024*1024:raise ValueError('Remote metadata response budget exceeded')
                    try:data=json.loads(text)
                    except ValueError:raise ValueError('Official source returned unsupported non-structured metadata') from None
                return data,('page' in properties)


def twentyfirst(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    position=int(after or 0)
    data,paged=asyncio.run(read_remote('search',key or f.get('query') or f.get('style') or 'components','',position//20+1,20))
    raw=data if isinstance(data,list) else next((data[k] for k in ['components','results','items'] if isinstance(data.get(k),list)),[])
    rows=[];consumed=position%20
    for x in raw[consumed if not key else 0:]:
        consumed+=1
        uid=str(x.get('id') or x.get('slug') or '')
        if not uid or len(uid)>200:continue
        if key and uid!=key:continue
        # Presentations only until per-component original reuse rights are
        # established. Drop all code, full prompt and generation response fields.
        previews=[];url=x.get('preview_url') or x.get('previewUrl') or x.get('image_url')
        if isinstance(url,str) and url.startswith('https://'):
            http.approve_content(url);previews=[{'url':url}]
        a=item(s['id'],uid,str(x.get('name') or x.get('title') or uid),'visual-reference',author=str(x.get('author_name') or ''),
               tags=[str(t.get('name','')) if isinstance(t,dict) else str(t) for t in x.get('tags',[])],previews=previews,
               description=str(x.get('description') or '')[:600],reference_preview=bool(previews),revision=str(x.get('updated_at') or ''))
        a['reference_category']='interface';a['original_access']='Account-authorized metadata only; original component licence not inferred'
        if key or matches(a,{**f,'query':''}):rows.append(a)
        if not key and len(rows)==limit:break
    if key:
        if not rows:raise ValueError('Official component metadata unavailable')
        return rows[0]
    n=position//20*20+consumed
    return {'items':rows,'next':str(n) if consumed<len(raw) or paged and len(raw)==20 else None,'total':None,
            'scope':'Official account-authorized 21st MCP metadata; no scrape, premium-code redistribution or hosted AI generation'}
