"""Local visual relevance. Only model software persists; embeddings never do."""
import hashlib,io,json,os
from functools import lru_cache
from pathlib import Path
MODEL={'repo':'Xenova/clip-vit-base-patch32','revision':'d15189d7028b43f1d3e65039190477f6af591c2a','license':'MIT','files':{
 'vision_model_quantized.onnx':('onnx/vision_model_quantized.onnx','583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299'),
 'text_model_quantized.onnx':('onnx/text_model_quantized.onnx','73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a'),
 'tokenizer.json':('tokenizer.json','f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd')}}
def model_path():return Path(os.environ.get('IC_STYLE_MODEL',str(Path.home()/'.cache/infinite-creativity/clip-style')))
def prepare(path):
    from .model_download import install
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,(remote,digest) in MODEL['files'].items():
        target=path/name
        install(MODEL['repo'],MODEL['revision'],remote,target,digest)
    (path/'provenance.json').write_text(json.dumps(MODEL,indent=2),encoding='utf-8')
@lru_cache(maxsize=1)
def model(path):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    path=Path(path)
    for name,(_,digest) in MODEL['files'].items():
        if not (path/name).exists() or hashlib.sha256((path/name).read_bytes()).hexdigest()!=digest:raise ValueError('Local visual ranking software unavailable; run prepare-live-style')
    options=ort.SessionOptions();options.intra_op_num_threads=2
    return (ort.InferenceSession(str(path/'vision_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider']),ort.InferenceSession(str(path/'text_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider']),Tokenizer.from_file(str(path/'tokenizer.json')))
def scores(direction,images):
    import numpy as np
    from PIL import Image
    vision,text,tokenizer=model(str(model_path()));tokenizer.enable_truncation(max_length=77)
    ids=np.array([tokenizer.encode(direction).ids],dtype=np.int64);inputs={'input_ids':ids,'attention_mask':np.ones_like(ids)}
    vector=text.run(None,{i.name:inputs[i.name] for i in text.get_inputs()})[0][0];vector/=max(float(np.linalg.norm(vector)),1e-9)
    result=[]
    for body in images:
        with Image.open(io.BytesIO(body)) as im:
            im=im.convert('RGB');w,h=im.size;side=min(w,h)
            im=im.crop(((w-side)//2,(h-side)//2,(w+side)//2,(h+side)//2)).resize((224,224),Image.Resampling.BICUBIC)
            pixels=np.asarray(im,dtype=np.float32)/255
        pixels=((pixels-np.array([.48145466,.4578275,.40821073]))/np.array([.26862954,.26130258,.27577711])).astype(np.float32).transpose(2,0,1)[None]
        image=vision.run(None,{vision.get_inputs()[0].name:pixels})[0][0];image/=max(float(np.linalg.norm(image)),1e-9)
        result.append(float(np.dot(vector,image)))
    return result
def rank(l,direction,asset_ids):
    if not direction.strip() or len(direction)>2048 or not 1<=len(asset_ids)<=12:raise ValueError('Supply an art direction and 1..12 item IDs')
    from .policy import normalize_query
    from .live_media_review import check_delivery
    rows=[];images=[];failures=[]
    for aid in dict.fromkeys(asset_ids):
        try:
            with l.content(aid,allow_reference_preview=True) as (library,local,a):
                preview=library.preview(local);body=Path(preview['path']).read_bytes()
                is_svg=body.lstrip().startswith((b'<svg',b'<?xml'))
                check_delivery({**a,'software_only':False},{'filename':'preview.svg' if is_svg else 'preview.png','role':'main','url':'current-preview'},preview['path'])
                if is_svg:
                    import cairosvg
                    body=cairosvg.svg2png(bytestring=body,output_width=512,output_height=512)
                images.append(body);rows.append(l.card(a))
        except Exception as e:failures.append({'asset_id':aid,'reason':str(e)[:250]})
    similarities=scores(normalize_query(direction),images) if images else []
    for a,score in zip(rows,similarities):a['visual_match']={'cosine_similarity':score,'basis':'Fresh admitted preview and local CLIP image/text embedding','scope':'Shown preview','model_revision':MODEL['revision']}
    rows.sort(key=lambda a:-a['visual_match']['cosine_similarity'])
    return {'items':rows,'unranked':failures,'art_direction':direction,'storage':'Request-only images/embeddings; no vector index or metadata cache','limits':'Relative visual relevance, not an aesthetic quality or safety probability. English briefs work best.'}
