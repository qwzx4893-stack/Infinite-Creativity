"""Pinned local ONNX image screening with explicit coverage and abstention."""
import hashlib
import json
import warnings
from pathlib import Path
from .catalog import now
from .curation import record

MODEL={'repo':'onnx-community/nsfw-image-detector-ONNX','revision':'6626debca038a8f7aa1729b1eaee3bd4eb929ad6','parent':'LukeJacob2023/nsfw-image-detector','license':'Apache-2.0','license_evidence':'https://huggingface.co/LukeJacob2023/nsfw-image-detector','files':{'model.onnx':{'remote':'onnx/model.onnx','sha256':'2605f68c77b9262e51afa0ff022971c7a8dabcfa51f55c78321b711b889b0e93'},'config.json':{'remote':'config.json','sha256':'3119b49239b1b8ca1c7ff693c6481e58e1d1553e284a70c01db2f9e6f9edf555'},'preprocessor_config.json':{'remote':'preprocessor_config.json','sha256':'b09d2030f83f2a59d12c717d41a9135a3f0c1ba0a2a5df694dbc40f77735daed'}}}

def prepare(path):
    from .model_download import install
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,f in MODEL['files'].items():
        target=path/name
        install(MODEL['repo'],MODEL['revision'],f['remote'],target,f['sha256'])
    (path/'provenance.json').write_text(json.dumps(MODEL,indent=2),encoding='utf-8')

class Screener:
    def __init__(self,path):
        import onnxruntime as ort
        self.path=Path(path)
        for name,f in MODEL['files'].items():
            p=self.path/name
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:raise ValueError('Pinned image model not installed; run prepare-vision')
        config=json.loads((self.path/'config.json').read_text())
        self.labels={int(k):v for k,v in config['id2label'].items()}
        if self.labels!={0:'drawings',1:'hentai',2:'neutral',3:'porn',4:'sexy'}:raise ValueError('Unexpected classifier label semantics')
        options=ort.SessionOptions();options.intra_op_num_threads=2
        self.session=ort.InferenceSession(str(self.path/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.input=self.session.get_inputs()[0].name

    def image(self,path):
        from PIL import Image,ImageOps
        import numpy as np
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width*image.height>40000000:raise ValueError('Image pixel budget exceeded')
                if getattr(image,'n_frames',1)!=1:raise ValueError('Animated image requires frame review')
                profile=image.info.get('icc_profile',b'')
                image=ImageOps.exif_transpose(image).convert('RGBA')
                # Hash complete decoded pixels, not PNG/JPEG container bytes.
                # Chunked rows avoid a second full float32 image allocation.
                pixel_hash=hashlib.sha256(('RGBA:'+str(image.size)).encode())
                if isinstance(profile,bytes):pixel_hash.update(hashlib.sha256(profile).digest())
                for y in range(0,image.height,256):pixel_hash.update(image.crop((0,y,image.width,min(y+256,image.height))).tobytes())
                sample=image.copy();sample.thumbnail((1024,1024))
                rgba=np.asarray(sample,dtype=np.float32);alpha=rgba[:,:,3]/255
                alpha_image=image.getchannel('A');histogram=alpha_image.histogram();visible_fraction=1-histogram[0]/(image.width*image.height)
                if not visible_fraction:raise ValueError('Fully transparent original contains no visible pixels; contextual/technical review needed')
                if not np.any(alpha):
                    sample=image.crop(alpha_image.getbbox());sample.thumbnail((1024,1024));rgba=np.asarray(sample,dtype=np.float32);alpha=rgba[:,:,3]/255
                luminance=float((rgba[:,:,:3].mean(axis=2)*alpha).sum()/alpha.sum()/255)
                backdrop='#202020' if luminance>.65 else '#ffffff'
                image=Image.alpha_composite(Image.new('RGBA',image.size,backdrop),image).convert('RGB')
        views=[image]
        if min(image.size)>=300:
            w,h=image.size;side=min(w,h)
            for x,y in {(0,0),(w-side,h-side),((w-side)//2,(h-side)//2)}:views.append(image.crop((x,y,x+side,y+side)))
        all_scores=[];predictions={}
        for view in views:
            # Pixel art remains crisp; a blur is not an accurate representation of its original pixels.
            sample=view.resize((224,224),Image.Resampling.NEAREST if min(view.size)<64 else Image.Resampling.BILINEAR)
            data=np.asarray(sample,dtype=np.float32)/255
            data=((data-.5)/.5).transpose(2,0,1)[None]
            key=hashlib.sha256(data.tobytes()).digest()
            if key not in predictions:
                logits=self.session.run(None,{self.input:data})[0][0];p=np.exp(logits-logits.max());p=p/p.sum()
                predictions[key]={self.labels[i]:float(p[i]) for i in range(len(p))}
            all_scores.append(predictions[key])
        risk=max(sum(p[k] for k in ('hentai','porn','sexy')) for p in all_scores)
        # Both high and ambiguous risk are quarantined. A model alone never permanently deletes.
        state='review-required' if risk>.02 else 'preview-screened'
        return {'scope':'preview-raster','state':state,'risk_probability':risk,'scores_by_view':all_scores,'views':len(views),'dimensions':list(image.size),'preprocess_version':'contrast-alpha-pixel-v3','decoded_pixel_sha256':pixel_hash.hexdigest(),'technical':{'visible_fraction_sampled':visible_fraction,'background_luminance_sampled':luminance,'interpretation':'Diagnostics, not artistic quality scores; no minimum style/detail threshold.'},'alpha_background':backdrop,'small_pixel_sampling':'nearest if either dimension <64; otherwise model bilinear','sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'model':{k:v for k,v in MODEL.items() if k!='files'},'model_sha256':MODEL['files']['model.onnx']['sha256'],'pass_threshold':.02,'at':now(),'limits':'This checks recorded image views only; unseen geometry, animation frames and contextual innuendo remain unverified.'}

def screen_catalog(c,limit=500,source='',model_path=None):
    from .library import Library
    if not 1<=limit<=100000:raise ValueError('Screening budget must be 1..100000')
    screener=Screener(model_path or c.path.parent/'models/nsfw-five-class');library=Library(c)
    checked=0;quarantined=0;failed=0
    rows=c.db.execute("SELECT a.id,a.kind,a.source,d.data,r.data review FROM assets a JOIN asset_details d ON d.asset_id=a.id LEFT JOIN curation r ON r.asset_id=a.id WHERE a.active=1 AND (?='' OR a.source=?) AND (r.data IS NULL OR r.data NOT LIKE '%\"vision\"%') ORDER BY coalesce(json_extract(r.data,'$.vision_attempt.at'),''),a.id",(source,source))
    try:
        for row in rows:
            d=json.loads(row['data']);a=c.get(row['id'])
            if not a['usable'] and not d.get('reference_preview'):continue
            originals=row['kind'] in {'sprite','texture','illustration','image','ui-asset'} and any(f.get('filename','').lower().endswith(('.png','.jpg','.jpeg','.webp')) for f in d.get('files',[])[:1])
            if not originals and not d.get('previews') and row['source'] not in {'polyhaven','ambientcg'}:continue
            if checked+failed>=limit:break
            try:
                r=library.file(row['id'],max_bytes=10*1024*1024) if originals else library.preview(row['id'])
                result=screener.image(r['path']);result['scope']='original-raster' if originals else 'preview-raster'
                record(c,row['id'],safety=result['state'],quality='technical-valid-original-raster' if originals else None,evidence={'vision':result});checked+=1;quarantined+=result['state']=='review-required'
            except Exception as e:
                failed+=1
                # Transport or unsupported-format failures do not imply that the content is safe.
                error=str(e).replace(str(c.path.parent.resolve()),'[private-state]')
                import re
                error=re.sub(r'(?i)gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+','[redacted]',error)
                record(c,row['id'],evidence={'vision_attempt':{'error':error[:300],'at':now(),'scope':'not-screened'}})
            if (checked+failed)%25==0:
                c.db.commit();print(json.dumps({'vision_progress':checked,'quarantined':quarantined,'failed':failed}),flush=True)
    finally:library.close()
    c.db.commit()
    return {'checked':checked,'quarantined':quarantined,'failed_or_unsupported':failed,'scope':'Individual recorded images, not whole unseen assets','remaining':'Read catalog_stats.curation.without_visual_review'}
