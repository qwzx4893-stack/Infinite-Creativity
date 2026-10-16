"""Automatic evidence, with separate technical, aesthetic and unknown states."""
import io,json,re,time
from functools import lru_cache
from importlib.resources import files
from pathlib import PurePosixPath,Path

@lru_cache(maxsize=2)
def language(tsx):
    from tree_sitter import Language
    import tree_sitter_typescript as grammar
    return Language(grammar.language_tsx() if tsx else grammar.language_typescript())

def inspect_source_bundle(records,dependencies=()):
    started=time.monotonic();checked=0;failures=[];unknown=[];imports=set()
    for name,record in records.items():
        text=record.get('_text');extension=PurePosixPath(name).suffix.lower()
        if not isinstance(text,str):unknown.append({'file':name,'reason':'Complete original text not supplied'});continue
        if not text.strip():failures.append({'file':name,'reason':'Empty original source'});continue
        if extension in {'.ts','.tsx','.js','.jsx','.mjs','.cjs'}:
            try:
                from tree_sitter import Parser
                encoded=text.encode();tree=Parser(language(extension in {'.tsx','.jsx'})).parse(encoded)
                if tree.root_node.has_error:failures.append({'file':name,'reason':'JavaScript/TypeScript syntax error or unsupported syntax'})
                else:checked+=1
                for node in tree.root_node.named_children:
                    if node.type!='import_statement':continue
                    literal=next((n for n in node.named_children if n.type=='string'),None)
                    if literal is None:continue
                    value=encoded[literal.start_byte:literal.end_byte].decode()[1:-1]
                    if not value.startswith(('.','/','@/','~/')):imports.add('/'.join(value.split('/')[:2]) if value.startswith('@') else value.split('/')[0])
            except ImportError:unknown.append({'file':name,'reason':'Local syntax parser unavailable; install the quality extra'})
        elif extension=='.json':
            try:json.loads(text);checked+=1
            except ValueError:failures.append({'file':name,'reason':'Invalid original JSON'})
        else:unknown.append({'file':name,'reason':'No structural parser for this format; presence/content policy checked only'})
    declared={re.sub(r'(?<!^)@[^/]*$','',str(v)) for v in dependencies}
    missing=sorted(imports-declared-{'react','react-dom','next'})
    # Host-project imports can be deliberate; they are explicit integration
    # requirements rather than proof that a component renders successfully.
    return {'state':'rejected' if failures else 'syntax-checked' if checked else 'unverified','parsed_source_files':checked,
            'syntax_failures':failures,'unparsed':unknown,'undeclared_package_imports':missing,
            'visual_design':'unverified-no-render','integration':'not-executed-not-installed',
            'milliseconds':round((time.monotonic()-started)*1000,2),
            'limits':'Parses complete code without executing it. Syntax, declared imports and bundle completeness do not certify responsive behaviour, accessibility or visual design.'}

def image_vector(body):
    import numpy as np
    from PIL import Image,ImageOps
    from .live_visual_rank import model,model_path
    vision,_,_=model(str(model_path()))
    with Image.open(io.BytesIO(body)) as im:
        im=ImageOps.exif_transpose(im).convert('RGB');im=ImageOps.fit(im,(224,224),method=Image.Resampling.BICUBIC)
        pixels=np.asarray(im,dtype=np.float32)/255
    pixels=((pixels-np.array([.48145466,.4578275,.40821073]))/np.array([.26862954,.26130258,.27577711])).astype(np.float32).transpose(2,0,1)[None]
    vector=vision.run(None,{vision.get_inputs()[0].name:pixels})[0][0]
    return vector/max(float(np.linalg.norm(vector)),1e-9)

@lru_cache(maxsize=1)
def aesthetic_head():
    import numpy as np
    data=json.loads(files('infinite_creativity').joinpath('data/aesthetic_vitb32.json').read_text(encoding='utf-8'))
    weights=np.asarray(data['weights'],dtype=np.float32)
    if weights.shape!=(512,) or not np.isfinite(weights).all() or not isinstance(data['bias'],(float,int)) or not np.isfinite(data['bias']):raise ValueError('Invalid pinned aesthetic software parameters')
    return data,weights

def score_raster(body):
    import numpy as np
    from PIL import Image
    started=time.monotonic()
    with Image.open(io.BytesIO(body)) as im:dimensions=list(im.size)
    head,weights=aesthetic_head();vector=image_vector(body)
    if vector.shape!=(512,) or not np.isfinite(vector).all():raise ValueError('Invalid local image embedding')
    score=float(np.dot(vector,weights)+head['bias'])
    return {'state':'estimated','score':round(score,4),'scale':'Uncalibrated raw LAION V1 aesthetic regression output, typically interpreted on an AVA-like 1..10 scale; not a probability.',
            'model_source':head['source'],'head_sha256':head['source_sha256'],'dimensions':dimensions,
            'milliseconds':round((time.monotonic()-started)*1000,2),
            'domain':'Photographic image aesthetics. Not validated for UI components, pixel art, PBR maps, icons, mesh topology, audio or animation craft.',
            'limits':'Population-preference estimate using a quantized CLIP encoder. Can be biased or wrong and does not guarantee professional quality.'}

def assess(library,asset_id,min_aesthetic=5.5):
    return assess_record(library,library.get(asset_id),asset_id,min_aesthetic)

def assess_record(library,a,asset_id,min_aesthetic=5.5):
    import math
    if isinstance(min_aesthetic,bool) or not isinstance(min_aesthetic,(int,float)) or not math.isfinite(min_aesthetic) or not 0<=min_aesthetic<=10:raise ValueError('Choose a finite aesthetic threshold 0..10')
    safety=a.get('admission',{}).get('safety',{});features=a.get('features',{})
    result={'asset_id':asset_id,'title':a['title'],'kind':a['kind'],'technical':{'state':'scope-checked' if safety else 'unverified','evidence':a.get('admission',{})},
            'publisher_evidence':features.get('quality_evidence'),'aesthetics':{'state':'unverified'},'professional_guarantee':False}
    if a.get('software_only'):
        if features.get('source_quality'):
            result['technical']=features['source_quality']
            result['aesthetics']={'state':'unverified','reason':'Fresh complete original source was parsed by the author-registry adapter. Rendered UI appearance was not evaluated.'}
            result.update(selection='rejected' if result['technical']['state']=='rejected' else 'visual-quality-unverified',min_aesthetic=min_aesthetic,storage='Fresh request-only original-source evidence; no quality index retained.')
            return result
        records={};dependencies=features.get('npm_dependencies',[])
        from .library import TEXT_FORMATS
        with library.content(asset_id) as (lib,local,metadata):
            total=0
            for f in lib.files(local)['files']:
                if f.get('role') in {'license','provenance'}:continue
                if f['format'] not in TEXT_FORMATS:continue
                original=lib.file(local,f['id'],2*1024*1024);body=Path(original['path']).read_bytes();total+=len(body)
                if len(records)>=40 or total>8*1024*1024:raise ValueError('Quality source inspection exceeds bundle budget')
                records[f.get('relative_path') or f['filename']]={'_text':body.decode('utf-8-sig')}
        result['technical']=inspect_source_bundle(records,dependencies)
        result['aesthetics']={'state':'unverified','reason':'No licensed rendered UI in the inspected scope. Source code and repository popularity cannot establish design quality.'}
    elif safety.get('scope')=='original-raster' and 'photography' in a.get('tags',[]):
        from .live_media_review import original_bytes
        source=next((f for f in a.get('files',[]) if f.get('role') in {'main','variant'}),None)
        if source:
            try:result['aesthetics']=score_raster(original_bytes(library.http,a,source,5*1024*1024))
            except (ImportError,FileNotFoundError,ValueError) as e:result['aesthetics']={'state':'unavailable','reason':str(e)[:200]}
    else:
        result['aesthetics']={'state':'not-scored-for-this-domain','reason':'Use type-specific original-media evidence; a photo-aesthetic model is not a valid universal score.'}
    technical=result['technical'].get('state')
    result['selection']='rejected' if technical=='rejected' else 'aesthetic-candidate' if result['aesthetics'].get('state')=='estimated' and result['aesthetics']['score']>=min_aesthetic else 'below-photo-aesthetic-threshold' if result['aesthetics'].get('state')=='estimated' else 'visual-quality-unverified'
    result['min_aesthetic']=min_aesthetic
    result['storage']='Fresh original evidence only; no item scores, screenshots, source bundles or embeddings retained between requests.'
    return result

def collect_quality(library,a,card,filters,report):
    """Run after safety/rights admission; uncertainty never becomes a high score."""
    report['evaluated']+=1
    try:assessment=assess_record(library,a,card['id'],filters.get('_min_aesthetic',5.5))
    except (ValueError,ImportError,OSError,RuntimeError) as error:
        assessment={'selection':'visual-quality-unverified','professional_guarantee':False,'aesthetics':{'state':'unavailable','reason':str(error)[:240]}}
    card['quality_assessment']=assessment
    selection=assessment['selection']
    if selection in {'rejected','below-photo-aesthetic-threshold'}:
        report['excluded']+=1;return 'excluded'
    if selection!='aesthetic-candidate':
        report['visually_unverified']+=1
        if filters.get('_require_visual_score',True):return 'queue'
    report['selected']+=1;return 'selected'
