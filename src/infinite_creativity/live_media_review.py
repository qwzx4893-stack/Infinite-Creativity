"""Local original-media review. Temporary bytes and verdicts die with the RPC.

The result always declares the inspected scope. This is an automatic admission
filter, not a promise of perfect detection of contextual sexual innuendo.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from .policy import acceptable,review_terms

SPEECH_MODEL={'repo':'Systran/faster-whisper-base','revision':'ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66','license':'MIT',
 'files':{'model.bin':'d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9','config.json':'56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a','tokenizer.json':'fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab','vocabulary.txt':'34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913'}}

def speech_path():return Path(os.environ.get('IC_SPEECH_MODEL',str(Path.home()/'.cache/infinite-creativity/whisper-base')))

def prepare_speech(path):
    from huggingface_hub import hf_hub_download
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,digest in SPEECH_MODEL['files'].items():
        target=path/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:continue
        downloaded=Path(hf_hub_download(SPEECH_MODEL['repo'],name,revision=SPEECH_MODEL['revision']))
        if hashlib.sha256(downloaded.read_bytes()).hexdigest()!=digest:raise ValueError('Pinned speech model checksum mismatch')
        shutil.copyfile(downloaded,target)
    (path/'provenance.json').write_text(json.dumps(SPEECH_MODEL,indent=2),encoding='utf-8')

@lru_cache(maxsize=1)
def speech_model(path):
    from faster_whisper import WhisperModel
    path=Path(path)
    for name,digest in SPEECH_MODEL['files'].items():
        if not (path/name).exists() or hashlib.sha256((path/name).read_bytes()).hexdigest()!=digest:raise ValueError('Local speech classifier software unavailable; run prepare-live-media')
    return WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)

def original_bytes(http,a,f,max_bytes=32*1024*1024):
    if f.get('bytes') and f['bytes']>max_bytes:raise ValueError('Original exceeds local review byte budget')
    if f.get('archive_entry'):
        from .content import ContentCache
        with tempfile.TemporaryDirectory(prefix='infinite-creativity-review-member-') as directory:
            cache=ContentCache(directory)
            container=a.get('containers',{}).get(f.get('container_id'))
            archive=cache.multipart_zip(container['parts']) if container and container['type']=='split-zip' else cache.remote_zip(f['url'])
            with archive as z:
                entry=z.getinfo(f['archive_entry'])
                if entry.file_size>max_bytes or entry.file_size>max(1,entry.compress_size)*500:raise ValueError('Archive member exceeds review budget')
                body=z.read(entry)
    else:body=http.read(f['url'],max_bytes)
    if f.get('sha256') and hashlib.sha256(body).hexdigest()!=f['sha256']:raise ValueError('Original SHA256 mismatch during review')
    if f.get('md5') and hashlib.md5(body).hexdigest()!=f['md5']:raise ValueError('Original checksum mismatch during review')
    return body

def image_check(image,classifier,directory,index):
    from PIL import Image
    if not isinstance(image,Image.Image):raise ValueError('Invalid decoded image')
    if image.width*image.height>40000000:raise ValueError('Decoded image exceeds pixel budget')
    path=Path(directory)/('view-'+str(index)+'.png');image.save(path)
    verdict=classifier.image(path)
    if verdict['state']!='preview-screened':raise ValueError('Original media sexual/suggestive classifier risk')
    return float(verdict.get('risk_probability',0))

def review_audio(body):
    import av
    import numpy as np
    from av.audio.resampler import AudioResampler
    frames=[];count=0;resampler=AudioResampler(format='fltp',layout='mono',rate=16000)
    with av.open(io.BytesIO(body)) as container:
        if not container.streams.audio:raise ValueError('Original has no audio stream')
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                block=converted.to_ndarray().reshape(-1);count+=len(block)
                if count>16000*90:raise ValueError('Audio exceeds complete review duration budget (90 seconds)')
                frames.append(block)
        for converted in resampler.resample(None):frames.append(converted.to_ndarray().reshape(-1))
    samples=np.concatenate(frames) if frames else np.array([],dtype=np.float32)
    if not len(samples) or not np.isfinite(samples).all():raise ValueError('Empty or invalid decoded audio')
    rms=float(np.sqrt(np.mean(samples*samples)));clipping=float(np.mean(np.abs(samples)>=.9999))
    if rms<1e-7 or clipping>.08:raise ValueError('Silent or severely clipped audio')
    segments,info=speech_model(str(speech_path())).transcribe(samples,task='translate',beam_size=1,condition_on_previous_text=False,vad_filter=True)
    transcript=[];started=time.monotonic()
    for segment in segments:
        if time.monotonic()-started>20:raise ValueError('Full speech review exceeded CPU budget')
        if not acceptable(segment.text) or review_terms(segment.text):raise ValueError('Audio speech sexual/suggestive content policy')
        transcript.append(segment.text)
    return {'scope':'entire decoded audio and multilingual speech translated to English; lexical sexual/suggestive screening','duration':len(samples)/16000,
            'speech_segments':len(transcript),'language':info.language,'rms':rms,'clipping_fraction':clipping,'model_revision':SPEECH_MODEL['revision'],
            'limits':'Speech recognition can miss words, music lyrics and nonverbal contextual innuendo; no transcript is retained or returned.'}

def review_frames(body,extension,classifier,directory):
    from PIL import Image
    risks=[];frames=0
    if extension in {'gif','webp','apng','png'}:
        with Image.open(io.BytesIO(body)) as im:
            total=getattr(im,'n_frames',1)
            if total>240:raise ValueError('Animation exceeds full-frame review budget (240 frames)')
            for i in range(total):
                im.seek(i);risks.append(image_check(im.convert('RGBA'),classifier,directory,i));frames+=1
        audio=None
    else:
        import av
        with av.open(io.BytesIO(body)) as container:
            if not container.streams.video:raise ValueError('Original has no video stream')
            has_audio=bool(container.streams.audio)
            for frame in container.decode(video=0):
                if frames>=240:raise ValueError('Video exceeds full-frame review budget (240 frames)')
                risks.append(image_check(frame.to_image(),classifier,directory,frames));frames+=1
        audio=review_audio(body) if has_audio else None
    if not frames:raise ValueError('Original contains no decoded frames')
    return {'scope':'all decoded original frames'+(' and complete audio track' if audio else ''),'frames':frames,'maximum_risk':max(risks),'audio':audio}

def review_vector(body,classifier,directory):
    from PIL import Image
    import cairosvg
    text=body.decode('utf-8-sig')
    if len(body)>2*1024*1024 or not acceptable(text) or review_terms(text):raise ValueError('Vector source content policy')
    # CairoSVG unsafe=False also forbids entity expansion. Deny URL fetches,
    # scripts, foreign markup and animation rather than let the renderer fetch.
    import re
    if re.search(r'<(?:script|foreignObject|animate\w*|set)\b|(?:href|src)\s*=\s*["\'](?!#)|url\(\s*(?!#)|<!DOCTYPE',text,re.I):raise ValueError('Vector external/active/animated content requires full review')
    png=cairosvg.svg2png(bytestring=body,output_width=512,output_height=512,unsafe=False)
    with Image.open(io.BytesIO(png)) as im:risk=image_check(im.convert('RGBA'),classifier,directory,0)
    return {'scope':'current SVG source and locally rendered complete static SVG','maximum_risk':risk}

def face_colors(mesh):
    import numpy as np
    visual=mesh.visual.to_color() if hasattr(mesh.visual,'to_color') else mesh.visual
    # Trimesh's converted visual can be detached from its mesh, leaving its
    # vertex/face counts unset for a combined textured scene.
    visual.mesh=mesh
    colors=np.asarray(visual.face_colors)
    return colors if len(colors)==len(mesh.faces) else np.tile([180,180,180,255],(len(mesh.faces),1))

def review_geometry(body,classifier,directory):
    """Inspect self-contained static GLB geometry, textures and six camera views."""
    import numpy as np
    import trimesh
    from PIL import Image,ImageDraw
    import struct
    if len(body)<20 or body[:4]!=b'glTF':raise ValueError('Invalid original GLB')
    version,total,length,kind=struct.unpack_from('<IIII',body,4)
    if version!=2 or total!=len(body) or kind!=0x4E4F534A or length>16*1024*1024 or 20+length>len(body):raise ValueError('Invalid original GLB JSON chunk')
    document=json.loads(body[20:20+length])
    if any(v.get('uri','').startswith(('http:','https:','file:')) for key in ('buffers','images') for v in document.get(key,[])):raise ValueError('External model dependencies require scoped review')
    scene=trimesh.load(io.BytesIO(body),file_type='glb',force='scene',process=False)
    risks=[];triangles=0;texture_count=0
    for geometry in scene.geometry.values():
        if not hasattr(geometry,'vertices') or not hasattr(geometry,'faces'):raise ValueError('Non-triangle geometry requires a different reviewer')
        if not np.isfinite(geometry.vertices).all():raise ValueError('Non-finite original geometry')
        triangles+=len(geometry.faces)
        if triangles>120000:raise ValueError('Geometry exceeds full rendering budget')
        material=getattr(geometry.visual,'material',None)
        for name in ('image','baseColorTexture','emissiveTexture'):
            texture=getattr(material,name,None)
            if texture is not None and hasattr(texture,'size'):
                risks.append(image_check(texture.convert('RGBA'),classifier,directory,texture_count));texture_count+=1
    mesh=scene.to_mesh()
    if not len(mesh.faces) or not len(mesh.vertices) or not np.ptp(mesh.vertices,axis=0).max()>0:raise ValueError('Empty or degenerate original mesh')
    vertices=np.asarray(mesh.vertices,dtype=float);vertices=(vertices-(vertices.min(axis=0)+vertices.max(axis=0))/2)/np.ptp(vertices,axis=0).max()
    faces=np.asarray(mesh.faces);colors=face_colors(mesh)
    if len(colors)!=len(faces):colors=np.tile([180,180,180,255],(len(faces),1))
    for i,(x,y,z) in enumerate([(0,1,2),(0,2,1),(1,2,0),(0,1,2),(0,2,1),(1,2,0)]):
        points=vertices[:,[x,y,z]].copy()
        if i>=3:points[:,0]*=-1;points[:,2]*=-1
        points[:,1]*=-1
        order=np.argsort(points[faces,2].mean(axis=1));im=Image.new('RGB',(384,384),'#ffffff');draw=ImageDraw.Draw(im)
        for face_index in order:
            polygon=[tuple(v) for v in (points[faces[face_index],:2]*330+192)]
            draw.polygon(polygon,fill=tuple(int(v) for v in colors[face_index,:3]))
        risks.append(image_check(im,classifier,directory,texture_count+i))
    pose_count=0
    if document.get('animations'):
        from .gltf_review import poses
        for vertices,faces,colors,clip,timestamp in poses(body):
            if len(faces)>120000:raise ValueError('Animated geometry exceeds rendering budget')
            vertices=(vertices-(vertices.min(axis=0)+vertices.max(axis=0))/2)/max(float(np.ptp(vertices,axis=0).max()),1e-9)
            for axis in [(0,1,2),(1,2,0)]:
                points=vertices[:,axis].copy();points[:,1]*=-1;im=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(im)
                for face_index in np.argsort(points[faces,2].mean(axis=1)):
                    draw.polygon([tuple(v) for v in points[faces[face_index],:2]*330+192],fill=tuple(int(np.clip(v,0,255)) for v in colors[face_index,:3]))
                risks.append(image_check(im,classifier,directory,texture_count+6+pose_count*2+axis[0]))
            pose_count+=1
    return {'scope':'self-contained original GLB, embedded textures, six static views'+(' and all declared keyframe/midpoint skin poses' if pose_count else ''),'triangles':triangles,'textures':texture_count,'rendered_views':6+pose_count*2,'animation_poses':pose_count,'maximum_risk':max(risks),'limits':'Discrete orthographic views can miss occluded detail or intermediate motion. Morph/cubic animations, external dependencies and files above bounded pose budgets are withheld.'}

def review_original(http,a,classifier):
    supported={'wav','ogg','mp3','flac','m4a','gif','webp','apng','mp4','webm','mov','svg','glb','exr','hdr'}
    files=[v for v in a.get('files',[]) if v.get('role') in {'main','variant'} and Path(v.get('filename','')).suffix.lstrip('.').lower() in supported]
    if not files:return None
    # Review the selected deliverable type. Variants remain declared; callers
    # receive only files whose bytes are re-reviewed at delivery.
    f=min(files,key=lambda v:v.get('bytes') or 12*1024*1024);ext=Path(f['filename']).suffix.lstrip('.').lower()
    body=original_bytes(http,a,f)
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-original-review-') as directory:
        if ext in {'wav','ogg','mp3','flac','m4a'}:result=review_audio(body)
        elif ext=='svg':result=review_vector(body,classifier,directory)
        elif ext=='glb':result=review_geometry(body,classifier,directory)
        else:result=review_frames(body,ext,classifier,directory)
    return {'state':'original-media-screened','scope':result['scope'],'evidence':result,'sha256':hashlib.sha256(body).hexdigest(),
            'file_identity':f.get('archive_entry') or f['url'],'checks':['sexual','suggestive','technical-quality'],'quality':{'state':'decoded-and-structurally-valid','limits':'No subjective aesthetic quality certification; intentional minimal/pixel/low-poly styles are preserved.'}}


def check_delivery(a,file,path):
    """Recheck the exact selected bytes, including an alternate variant."""
    if os.environ.get('IC_SAFETY_MODE','strict')!='strict':return
    from .live_admission import screener,model_path
    from .library import TEXT_FORMATS
    body=Path(path).read_bytes();ext=Path(file['filename']).suffix.lstrip('.').lower()
    if file.get('role') in {'license','provenance'} or a.get('software_only') or ext in TEXT_FORMATS-{'svg','obj','gltf'}:return
    evidence=a.get('admission',{}).get('safety',{})
    if evidence.get('state')=='original-media-screened' and evidence.get('sha256')==hashlib.sha256(body).hexdigest():return
    classifier=None if ext in {'wav','ogg','mp3','flac','m4a'} else screener(str(model_path()))
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-delivery-review-') as directory:
        if ext in {'png','jpg','jpeg','webp','apng','gif'}:
            from PIL import Image
            with Image.open(io.BytesIO(body)) as image:
                if getattr(image,'n_frames',1)>1:review_frames(body,ext,classifier,directory)
                else:image_check(image.convert('RGBA'),classifier,directory,0)
            return
        class BytesHTTP:
            def read(self,*args):return body
        candidate={**a,'files':[{**file,'archive_entry':None,'container_id':None}]}
        verdict=review_original(BytesHTTP(),candidate,classifier)
        if verdict:return
    raise ValueError('Selected original format needs full content review; a safe cover does not authorize unseen variants. Choose a reviewed raster, SVG, audio, video or static GLB member.')

def render_glb_preview(body):
    """Internal CPU preview of a previously reviewed original, with no UI."""
    import numpy as np
    import trimesh
    from PIL import Image,ImageDraw
    mesh=trimesh.load(io.BytesIO(body),file_type='glb',force='scene',process=False).to_mesh()
    if len(mesh.faces)>120000:raise ValueError('Preview geometry exceeds rendering budget')
    vertices=np.asarray(mesh.vertices,dtype=float);vertices=(vertices-(vertices.min(axis=0)+vertices.max(axis=0))/2)/max(float(np.ptp(vertices,axis=0).max()),1e-9)
    horizontal=np.array([1,0,-1])/np.sqrt(2);vertical=np.array([1,-2,1])/np.sqrt(6);depth=np.array([1,1,1])/np.sqrt(3)
    points=vertices@np.stack([horizontal,vertical,depth],axis=1)
    colors=face_colors(mesh)
    if len(colors)!=len(mesh.faces):colors=np.tile([160,160,180,255],(len(mesh.faces),1))
    image=Image.new('RGB',(512,512),'#eef0f5');draw=ImageDraw.Draw(image)
    for face_index in np.argsort(points[mesh.faces,2].mean(axis=1)):
        polygon=[tuple(v) for v in points[mesh.faces[face_index],:2]*380+256]
        draw.polygon(polygon,fill=tuple(int(v) for v in colors[face_index,:3]))
    result=io.BytesIO();image.save(result,format='PNG');return result.getvalue()
