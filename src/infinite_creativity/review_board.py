"""One temporary native MCP image for an agent's visual curation decision."""
import base64,io,math
from concurrent.futures import ThreadPoolExecutor
from .request_scope import context_map
from pathlib import Path
from .live import unseal
from .live_media_review import check_delivery,image_check

def board(library,asset_ids):
    if not 1<=len(asset_ids)<=8 or len(set(asset_ids))!=len(asset_ids):raise ValueError('Choose 1..8 distinct current asset locators')
    from PIL import Image,ImageOps,ImageDraw
    tiles=[];items=[];failures=[]
    def load(aid):
        owned=hasattr(library,'sources');local=type(library)(configs=library.sources) if owned else library
        try:
            if unseal(aid,'asset').get('review'):
                from .selected_review import preview as selected_preview
                result=selected_preview(local,aid);pixels=result.get('_preview_png')
                if not pixels:raise ValueError('Selected original has no generated raster preview')
                body=base64.b64decode(pixels);item=local.item(aid)
            else:
                with local.content(aid,allow_reference_preview=True) as (lib,key,a):
                    preview=lib.preview(key);body=Path(preview['path']).read_bytes();vector=body.lstrip().startswith((b'<svg',b'<?xml'))
                    check_delivery({**a,'software_only':False},{'filename':'preview.svg' if vector else 'preview.png','role':'main','url':'current-preview'},preview['path'])
                    if vector:
                        import cairosvg
                        body=cairosvg.svg2png(bytestring=body,output_width=512,output_height=512)
                    item=local.card(a)|{'id':aid}
            return body,item,None
        except Exception as e:return None,None,{'asset_id':aid,'reason':str(e)[:250]}
        finally:
            if owned:local.close()
    with ThreadPoolExecutor(max_workers=3) as pool:loaded=list(context_map(pool,load,asset_ids))
    for aid,(body,item,error) in zip(asset_ids,loaded):
        if error:failures.append(error);continue
        try:
            with Image.open(io.BytesIO(body)) as image:
                pixels=image.convert('RGBA');tile=Image.new('RGB',(384,280),'#eeeeee');pixels=ImageOps.contain(pixels,(368,236));tile.paste(pixels,((384-pixels.width)//2,(244-pixels.height)//2),pixels)
                number=len(tiles)+1;ImageDraw.Draw(tile).text((12,255),'#'+str(number),fill='#111111');tiles.append(tile)
            items.append({'tile':number,'id':aid,'title':item['title'],'kind':item['kind'],'source':item['source'],'section_id':item['section_id'],'license':item['license'],'license_url':item['license_url'],'admission':item.get('admission',{}),'access':item.get('access'),'actions':['get_library_item']+(['asset_files'] if item.get('access') in {'usable','usable-for-end-product'} else [])})
        except Exception as e:failures.append({'asset_id':aid,'reason':str(e)[:250]})
    if not tiles:return {'items':[],'unavailable':failures,'storage':'No preview data retained'},None
    columns=min(3,len(tiles));rows=math.ceil(len(tiles)/columns);canvas=Image.new('RGB',(columns*384,rows*280),'#dddddd')
    for i,tile in enumerate(tiles):canvas.paste(tile,((i%columns)*384,(i//columns)*280))
    import tempfile
    from .live_admission import screener,model_path
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-review-board-') as directory:image_check(canvas,screener(str(model_path())),directory,'board')
    output=io.BytesIO();canvas.save(output,format='PNG')
    if output.tell()>2*1024*1024:raise ValueError('Comparison image exceeds native MCP byte budget; choose fewer items')
    return {'items':items,'unavailable':failures,'scope':'Current screened preview views, not complete asset surfaces/animations. Tile numbers map to metadata. Reference-only tiles convey no original reuse rights.','decision':'Compare visual quality, craft, consistency and requested art direction. No automatic aesthetic score is claimed.','storage':'Request-only source images/composite. No preview gallery, asset cache or image index is written.'},base64.b64encode(output.getvalue()).decode()
