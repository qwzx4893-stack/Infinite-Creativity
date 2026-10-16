"""Real stdio acceptance checks. Prints metrics, never saves original assets.

Uses prepared local media software via the normal IC_* environment variables.
Example: python scripts/verify_live_workflows.py --case model --case material
"""
import argparse,asyncio,base64,hashlib,json,os,sys,time
from datetime import timedelta
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from infinite_creativity.live import source_configs

CASES={'model':('polypizza','tree'),'material':('texturecan','wood'),'met':('met-open-access','landscape'),'cleveland':('cleveland-open-access','landscape'),'audio':('incompetech','Discovery Hit'),'interface':('','accordion'),
       'millionth-art':('pd3m',''),'curated-model':('objaverse-curated','fisherman'),'instrument':('meta-open-sound','piano'),
       'transition':('gl-transitions','Bounce'),'motion-code':('manim-motion-examples','basic'),
       'agent-elements':('registry:agent-elements','tool-group'),'magicui':('registry:magicui','aurora-text'),'shadcn':('registry:shadcn','button'),'photo-quality':('pd3m','photo')}

async def verify(cases,probe_sources=False):
    params=StdioServerParameters(command=sys.executable,args=['-m','infinite_creativity.server'],env=dict(os.environ))
    failures=0
    async with stdio_client(params) as (read,write),ClientSession(read,write,read_timeout_seconds=timedelta(seconds=600)) as session:
        await session.initialize();print(json.dumps({'mcp_tools':len((await session.list_tools()).tools)}),flush=True)
        async def call(name,args):
            result=await session.call_tool(name,args)
            if result.isError:raise ValueError(name+': '+str(result.content)[:400])
            return result
        for name in cases:
            started=time.monotonic()
            try:
                source,query=CASES[name]
                if name=='interface':source=next(s['id'] for s in source_configs().values() if s.get('repo','').lower()=='ibelick/motion-primitives')
                view=(await call('browse_asset_catalog',{'source':source,'offset':2000000,'limit':1}) if name=='millionth-art' else await call('open_library',{'source':source,'query':query,'limit':1})).structuredContent
                candidates=view['items']+view.get('review_queue',[])
                for _ in range(2):
                    if candidates or not view.get('next_cursor'):break
                    view=(await call('library_page',{'cursor':view['next_cursor'],'limit':1})).structuredContent;candidates=view['items']+view.get('review_queue',[])
                if not candidates:raise ValueError('No admitted/pending candidate: '+json.dumps({'withheld':view.get('admission',{}).get('withheld_reasons',{}),'source_errors':[s.get('reason') or s.get('item_errors') for s in view.get('sources',[]) if s.get('reason') or s.get('item_errors')]})[:350])
                selected=candidates[0]
                if name in {'material','instrument'}:
                    pack=(await call('get_library_pack',{'pack_id':selected['pack_id'],'limit':2})).structuredContent['view'];members=pack['items']+pack.get('review_queue',[])
                    if not members:raise ValueError('Current pack has no reviewable map in this window')
                    if name=='instrument' and pack['sources'][0].get('catalog',{}).get('collections_in_scope')!=['meta-piano']:raise ValueError('Instrument pack includes unrelated collection members')
                    selected=members[0]
                progress=[]
                async def update(value,total,message):progress.append(value)
                result=await session.call_tool('open_asset_package',{'asset_id':selected['id'],'length':65536},progress_callback=update)
                if result.isError:raise ValueError('open_asset_package: '+str(result.content)[:400])
                data=result.structuredContent;package=data['package'];original=package['original'];body=base64.b64decode(original['data']);full=original['next_offset'] is None
                if not body or full and hashlib.sha256(body).hexdigest()!=original['sha256']:raise ValueError('Inline original integrity/window failure')
                if not all(a<b for a,b in zip(progress,progress[1:])):raise ValueError('Non-monotonic MCP review progress')
                native=[block.type for block in result.content]
                if name in {'audio','instrument'} and 'audio' not in native:raise ValueError('Listening excerpt missing from reviewed sound package')
                if name not in {'audio','instrument','interface','transition','motion-code','agent-elements','magicui','shadcn'} and 'image' not in native:raise ValueError('Screened native preview missing')
                if name in {'agent-elements','magicui','shadcn'}:
                    bundle=(await call('fetch_asset_bundle',{'asset_id':selected['id']})).structuredContent
                    if not any(f['role']=='license' for f in bundle['files']):raise ValueError('Original author MIT notice missing')
                    for f in bundle['files']:
                        if hashlib.sha256(base64.b64decode(f['data'])).hexdigest()!=f['sha256']:raise ValueError('Dependency/notice bundle digest mismatch')
                    quality=(await call('assess_asset_quality',{'asset_id':selected['id']})).structuredContent
                    if quality['technical']['state']!='syntax-checked' or quality['aesthetics']['state']!='unverified':raise ValueError('Incorrect source/visual quality evidence')
                    strict=(await call('curate_library',{'source':source,'query':query,'limit':1})).structuredContent
                    if strict['items'] or not strict['quality_queue']:raise ValueError('Unrendered UI was falsely certified or lost')
                    relaxed=(await call('curate_library',{'source':source,'query':query,'limit':1,'require_visual_score':False})).structuredContent
                    if not relaxed['items']:raise ValueError('Explicitly unverified source candidate is inaccessible')
                    print(json.dumps({'case':name+'-dependencies-quality','status':'passed','files_with_notices':len(bundle['files']),'bundle_bytes':bundle['total_bytes'],'parsed_files':quality['technical']['parsed_source_files'],'strict_visual_queue':len(strict['quality_queue']),'relaxed_unverified_items':len(relaxed['items'])}),flush=True)
                print(json.dumps({'case':name,'status':'passed','seconds':round(time.monotonic()-started,3),'format':data['format'],'reviewed_files':data['reviewed_files'],'reviewed_bytes':data['reviewed_bytes'],'inline_bytes':len(body),'complete_inline_original':full,'native_blocks':native,'progress_notifications':len(progress),'metadata_http':data.get('performance',{})}),flush=True)
                if name=='photo-quality':
                    assessment=(await call('assess_asset_quality',{'asset_id':selected['id'],'min_aesthetic':0})).structuredContent
                    if assessment['aesthetics']['state']!='estimated' or assessment['professional_guarantee']:raise ValueError('Original photographic score unavailable/misstated: '+json.dumps(assessment['aesthetics']))
                    low=(await call('curate_library',{'source':source,'query':query,'limit':1,'min_aesthetic':0})).structuredContent
                    high=(await call('curate_library',{'source':source,'query':query,'limit':1,'min_aesthetic':10})).structuredContent
                    if not low['items'] or high['items'] or high['quality']['excluded']!=1:
                        evidence=[{'quality':v.get('quality'),'admission':v.get('admission'),'source_errors':[s.get('reason') for s in v.get('sources',[]) if s.get('reason')],'unscored':[x['quality_assessment'].get('aesthetics') for x in v.get('quality_queue',[])]} for v in (low,high)]
                        raise ValueError('Photo threshold check failed or original temporarily unavailable: '+json.dumps(evidence))
                    print(json.dumps({'case':'photo-aesthetic-filter','status':'passed','raw_regression_score':assessment['aesthetics']['score'],'score_milliseconds':assessment['aesthetics']['milliseconds'],'threshold_0_selected':len(low['items']),'threshold_10_excluded':high['quality']['excluded'],'professional_guarantee':False}),flush=True)
                if name in {'audio','instrument'}:
                    listening=await call('preview_audio_asset',{'asset_id':data['asset_id'],'file_id':data['selected_file_id'],'start_seconds':1,'duration_seconds':1})
                    if not any(b.type=='audio' for b in listening.content):raise ValueError('Fresh digest-verified listening preview missing')
                    print(json.dumps({'case':'audio-revalidation','status':'passed','start_seconds':1,'duration_seconds':1,'native_blocks':[b.type for b in listening.content]}),flush=True)
            except Exception as e:
                failures+=1;print(json.dumps({'case':name,'status':'failed-or-withheld','seconds':round(time.monotonic()-started,3),'reason':str(e)[:500]}),flush=True)
        if probe_sources:
            response=await call('probe_library_sources',{'source_ids':['met-open-access','cleveland-open-access'],'query':'landscape','limit_per_source':1})
            print(json.dumps({'source_probe':[{'source':s['source'],'state':s['state'],'seconds':s['seconds']} for s in response.structuredContent['sources']]}),flush=True)
    return failures

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',action='append',choices=CASES);parser.add_argument('--probe',action='store_true');args=parser.parse_args()
    raise SystemExit(1 if asyncio.run(verify(args.case or list(CASES),args.probe)) else 0)
