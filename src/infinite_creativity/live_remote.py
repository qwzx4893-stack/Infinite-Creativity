"""Read-only metadata federation through a first-party MCP service."""
import asyncio,json,os
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def request(endpoint,token,tool,arguments):
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token},timeout=12) as client:
        async with streamable_http_client(endpoint,http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize();result=await session.call_tool(tool,arguments)
                if result.isError:raise ValueError('Official source MCP rejected the request; access limits are not bypassed')
                if result.structuredContent:return result.structuredContent
                text=next((c.text for c in result.content if c.type=='text'),'')
                try:return json.JSONDecoder().raw_decode(text)[0]
                except ValueError:raise ValueError('Official source returned an unsupported metadata format') from None

def motionsites(http,s,f,after,limit,key=None):
    from .live_providers import item,matches
    token=os.environ.get('IC_MOTIONSITES_TOKEN')
    if not token:raise ValueError('MotionSites requires official account OAuth authorization. Supply IC_MOTIONSITES_TOKEN from your authorized connection; no account access is bypassed or shared.')
    endpoint='https://xgdzyqfalbibzelpdpvr.supabase.co/functions/v1/mcp'
    query=key.replace('-',' ') if key else f.get('query','')
    tool='search_prompts' if query else 'list_prompts'
    arguments={'query':query,'limit':50 if key else limit} if query else {'access':'any','limit':limit,'offset':int(after or 0)}
    data=asyncio.run(request(endpoint,token,tool,arguments));rows=[]
    for p in data.get('results',[]):
        if key and p.get('id')!=key:continue
        preview=p.get('preview_url')
        a=item(s['id'],p['id'],p.get('title',p['id']),'visual-reference','unknown','https://motionsites.ai/terms','MotionSites',[p.get('category',''),p.get('kind',''),p.get('access','')],previews=[{'url':preview}] if preview else [],description='Official source metadata and presentation preview only; full paid prompts are not copied or exposed as reusable originals.',reference_preview=bool(preview));a['reference_category']='interface'
        if matches(a,f):rows.append(a)
    if key:
        if not rows:raise ValueError('Prompt metadata unavailable under current account rights')
        return rows[0]
    return {'items':rows,'next':str(int(after or 0)+len(data.get('results',[]))) if not query and len(data.get('results',[]))==limit else None,'total':None,'scope':'Official account-authorized MCP metadata; paid prompt originals excluded','provider_notice':data.get('upgrade_cta')}
