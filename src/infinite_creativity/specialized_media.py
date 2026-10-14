"""Local specialized original readers; no saved catalogue or original files."""
import io,json,os,posixpath,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path,PurePosixPath
from .policy import acceptable,review_terms
from .review_limits import limits,progress

NATIVE={'blend','fbx','usd','usda','usdc','usdz','abc','bvh'}
LAYERED={'psd','psb','ora'}
MESH={'obj','ply','stl','off','3mf','dae'}

def blender_path():
    configured=os.environ.get('IC_BLENDER_PATH')
    if configured:
        if not Path(configured).is_file():raise ValueError('Configured local Blender executable is unavailable')
        return str(Path(configured).resolve())
    found=shutil.which('blender')
    if found:return found
    if os.name=='nt':
        base=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Blender Foundation'
        choices=sorted(base.glob('Blender */blender.exe'),reverse=True) if base.exists() else []
        if choices:return str(choices[0])
    return None

def native_convert(path,directory):
    executable=blender_path()
    if not executable:raise ValueError('Local Blender is required for this native original; set IC_BLENDER_PATH')
    target=Path(tempfile.mkdtemp(prefix='native-conversion-',dir=directory))
    configuration={'input':str(Path(path).resolve()),'output':str(target.resolve()),'staging_root':str(Path(directory).resolve()),'limits':limits()}
    request=target/'request.json';request.write_text(json.dumps(configuration),encoding='utf-8')
    script=Path(__file__).with_name('native_blender_worker.py')
    cmd=[executable,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--',str(request)]
    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    progress(0,1,'Reading native original with local Blender; source scripts are disabled')
    # Only our fixed software script executes. Asset paths are separate argv
    # entries, never interpolated commands or evaluated source text.
    with tempfile.TemporaryFile() as log:
        env={k:v for k,v in os.environ.items() if k not in {'GH_TOKEN','GITHUB_TOKEN','BLENDERKIT_TOKEN'} and not k.startswith('GIT_CONFIG_')}
        with subprocess.Popen(cmd,cwd=directory,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,creationflags=creationflags) as process:
            started=time.monotonic()
            try:
                while process.poll() is None:
                    try:process.wait(timeout=.5)
                    except subprocess.TimeoutExpired:progress(time.monotonic()-started,limits()['cpu_seconds'],'Local native reader is processing the selected file')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
            code=process.returncode
    report_path=target/'report.json'
    if not report_path.exists():raise ValueError('Local Blender could not inspect/convert this original')
    report=json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('error'):raise ValueError('Native original withheld: '+report['error'][:200])
    if code:raise ValueError('Local Blender conversion failed')
    if not acceptable(' '.join(report.get('names',[]))) or review_terms(' '.join(report.get('names',[]))):raise ValueError('Native object/material/bone names violate content policy')
    converted=target/'converted.glb'
    if not converted.exists() or converted.stat().st_size>limits()['bytes']:raise ValueError('Converted native representation exceeds review budget')
    progress(1,1,'Native geometry, materials and animation converted for review')
    return converted,report,target

def review_layered(path,extension,classifier,directory):
    from PIL import Image
    from .live_media_review import image_check
    risk=[];layers=0;preview=None
    if extension in {'psd','psb'}:
        from psd_tools import PSDImage
        document=PSDImage.open(path)
        if document.width*document.height>limits()['pixels']:raise ValueError('Layered original exceeds pixel budget')
        if document.has_preview():
            image=document.topil()
            if image is not None:risk.append(image_check(image.convert('RGBA'),classifier,directory,'composite'));preview=image.convert('RGBA')
        for layer in document.descendants():
            layers+=1
            if layers>limits()['layers']:raise ValueError('Layered original exceeds layer budget')
            if not acceptable(layer.name) or review_terms(layer.name):raise ValueError('Layer names violate content policy')
            if layer.kind=='type' and (not acceptable(layer.text) or review_terms(layer.text)):raise ValueError('Stored text layer violates content policy')
            if layer.kind=='smartobject':
                smart=layer.smart_object
                if smart.kind!='data':raise ValueError('Externally linked smart objects require their scoped originals')
                body=smart.data
                if len(body)>limits()['bytes']:raise ValueError('Embedded smart object exceeds budget')
                if body.startswith(b'8BPS'):raise ValueError('Nested layered smart objects need their own complete layer review')
                with Image.open(io.BytesIO(body)) as image:risk.append(image_check(image.convert('RGBA'),classifier,directory,'embedded-'+str(layers)))
            if layer.has_pixels():
                image=layer.topil()
                if image is not None:risk.append(image_check(image.convert('RGBA'),classifier,directory,layers))
            elif layer.kind in {'type','shape'}:
                image=layer.composite(force=True)
                if image is None:raise ValueError('Stored vector/text layer has no complete local rendering')
                risk.append(image_check(image.convert('RGBA'),classifier,directory,layers))
            elif layer.kind not in {'group','adjustment','fill'}:raise ValueError('Layer type has no complete local reviewer')
            progress(layers,limits()['layers'],'Reviewing every stored layer, including hidden layers')
    else:
        with zipfile.ZipFile(path) as archive:
            selected=[v for v in archive.infolist() if v.filename.lower().endswith(('.png','.jpg','.jpeg'))]
            from defusedxml import ElementTree
            stack=archive.read('stack.xml') if 'stack.xml' in archive.namelist() else None
            if stack:
                text=stack.decode('utf-8-sig')
                if not acceptable(text) or review_terms(text):raise ValueError('Layer stack metadata violates content policy')
                document=ElementTree.fromstring(stack)
                names={v.filename for v in selected}
                if any(layer.get('src') not in names for layer in document.iter('layer')):raise ValueError('Original layer pixels are missing or unsupported')
            if len(selected)>limits()['layers']:raise ValueError('Layered archive exceeds layer budget')
            for v in selected:
                if not acceptable(v.filename) or review_terms(v.filename):raise ValueError('Layer member violates content policy')
                if v.file_size>limits()['bytes'] or v.file_size>max(1,v.compress_size)*500:raise ValueError('Layer member exceeds bounded decode budget')
                with Image.open(io.BytesIO(archive.read(v))) as image:
                    risk.append(image_check(image.convert('RGBA'),classifier,directory,layers))
                    if v.filename=='mergedimage.png' or preview is None:preview=image.convert('RGBA')
                layers+=1;progress(layers,len(selected),'Reviewing original raster layers')
            if extension=='kra':
                # Krita native raster tiles are not reliably represented by a
                # merged PNG. Never certify unseen native paint/vector layers.
                unknown=[n for n in archive.namelist() if re_search_krita_layer(n)]
                if unknown:raise ValueError('Krita native tiled/vector layers need a specialized complete layer renderer')
    if not risk:raise ValueError('Layered file contains no screenable original pixels')
    result={'scope':'original stored composite and all decoded raster/embedded-image layers, including hidden layers','layers':layers,'maximum_risk':max(risk),'limits':'Externally linked or non-image smart objects and unrendered native layers are withheld.'}
    if preview is not None:
        preview.thumbnail((512,512));image_check(preview,classifier,directory,'layer-preview');body=io.BytesIO();preview.save(body,format='PNG');result['_preview_bytes']=body.getvalue()
    return result

def re_search_krita_layer(name):
    import re
    return bool(re.search(r'(?:^|/)(?:layer\d+|vector)\b',name,re.I)) and not name.endswith('.png')

def review_mesh(path,extension,classifier,directory):
    import trimesh
    from .live_media_review import review_geometry
    if extension=='dae':
        text=Path(path).read_text(encoding='utf-8-sig')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('Collada active XML declarations are unsupported')
        from defusedxml import ElementTree
        doc=ElementTree.fromstring(text)
        if any(node.tag.endswith(('library_animations','library_controllers')) and len(node) for node in doc.iter()):raise ValueError('Animated/skinned Collada requires a specialized temporal native reader')
        for node in doc.iter():
            if node.tag.endswith('init_from') and node.text and node.text.strip() and not node.text.strip().startswith('#'):
                value=node.text.strip()
                # Surface references name a local image ID; texture paths must
                # be explicitly staged within this request.
                if '/' not in value and '.' not in value:continue
                referenced=(Path(path).parent/value).resolve()
                if ':' in value or not referenced.is_relative_to(Path(directory).resolve()) or not referenced.is_file():raise ValueError('Collada external image is outside current licensed staging')
    scene=trimesh.load(path,file_type=extension,force='scene',process=False)
    body=scene.export(file_type='glb')
    result=review_geometry(body,classifier,directory)
    target=Path(directory)/'converted-mesh.glb';target.write_bytes(body)
    return {**result,'_converted_glb':str(target),'scope':'current original '+extension.upper()+' geometry/materials converted locally; '+result['scope']}

def review_path(path,extension,classifier,directory):
    from .live_media_review import review_geometry,review_frames,review_audio,review_vector,image_check
    if extension in LAYERED:return review_layered(path,extension,classifier,directory)
    if extension in NATIVE:
        converted,report,root=native_convert(path,directory)
        result=review_geometry(converted.read_bytes(),classifier,directory)
        for i,texture in enumerate(sorted(root.glob('texture-*.png'))):
            from PIL import Image
            with Image.open(texture) as image:image_check(image.convert('RGBA'),classifier,directory,'native-texture-'+str(i))
        return {**result,'native':report,'_converted_glb':str(converted),'scope':'current native '+extension.upper()+' read with scripts disabled, packed/staged textures and converted geometry/animation; '+result['scope']}
    if extension in MESH:return review_mesh(path,extension,classifier,directory)
    if extension=='gltf':
        # All external relative buffers/textures must already be explicitly
        # licence-scoped and staged by selected_review. Never fetch from JSON.
        import trimesh
        document=json.loads(Path(path).read_text(encoding='utf-8'))
        for name in ('buffers','images'):
            for entry in document.get(name,[]):
                uri=entry.get('uri','')
                if uri.startswith('data:'):continue
                if ':' in uri or uri.startswith(('/','\\')):raise ValueError('GLTF may only use explicitly staged relative dependencies')
                referenced=(Path(path).parent/uri).resolve()
                if not referenced.is_relative_to(Path(directory).resolve()) or not referenced.is_file():raise ValueError('GLTF dependency is missing or leaves the scoped staging directory')
        if document.get('animations'):
            converted,report,_=native_convert(path,directory);body=converted.read_bytes()
        else:body=trimesh.load(path,force='scene',process=False).export(file_type='glb');report=None
        result=review_geometry(body,classifier,directory)
        target=Path(directory)/'converted-gltf.glb';target.write_bytes(body)
        return {**result,'native':report,'_converted_glb':str(target),'scope':'original GLTF plus explicitly scoped staged buffers/textures; '+result['scope']}
    if extension in {'wav','ogg','mp3','flac','m4a','aac','aiff','aif','opus'}:return review_audio(path)
    if extension in {'png','jpg','jpeg','bmp','tif','tiff','dds'}:
        from PIL import Image
        if extension=='dds':
            import struct
            with Path(path).open('rb') as stream:header=stream.read(148)
            if len(header)<128 or struct.unpack_from('<I',header,28)[0]>1 or struct.unpack_from('<I',header,112)[0]&0x20FE00 or header[84:88]==b'DX10' and (len(header)<148 or struct.unpack_from('<I',header,140)[0]>1):raise ValueError('DDS cube/volume/array/mip payload requires complete specialized review')
        with Image.open(path) as image:
            count=getattr(image,'n_frames',1)
            if count>limits()['frames']:raise ValueError('Multi-page raster exceeds complete page budget')
            risks=[];preview=None
            for i in range(count):
                image.seek(i);pixels=image.convert('RGBA');risks.append(image_check(pixels,classifier,directory,i))
                if preview is None:preview=pixels.copy()
            preview.thumbnail((512,512));image_check(preview,classifier,directory,'raster-preview');body=io.BytesIO();preview.save(body,format='PNG')
            return {'scope':'all decoded original raster pages/frames','frames':count,'maximum_risk':max(risks),'_preview_bytes':body.getvalue()}
    if extension=='glb':return review_geometry(Path(path).read_bytes(),classifier,directory)
    if extension=='svg':return review_vector(Path(path).read_bytes(),classifier,directory)
    if extension in {'mp4','webm','mov','mkv','avi','gif','webp','apng','exr','hdr'}:return review_frames(path,extension,classifier,directory)
    raise ValueError('No complete local original reviewer for '+extension)
