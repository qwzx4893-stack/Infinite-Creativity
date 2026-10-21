"""Local original-media review. Temporary bytes and verdicts die with the RPC.

The result always declares the inspected scope. This is an automatic admission
filter, not a promise of perfect detection of contextual sexual innuendo.
"""
import hashlib
import io
import json
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from .policy import acceptable,review_terms
from .review_limits import limits,progress,profile

def media_input(body):
    return str(body) if isinstance(body,(Path,str)) else io.BytesIO(body)

SPEECH_MODEL={'repo':'Systran/faster-whisper-base','revision':'ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66','license':'MIT',
 'files':{'model.bin':'d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9','config.json':'56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a','tokenizer.json':'fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab','vocabulary.txt':'34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913'}}

def speech_path():return Path(os.environ.get('IC_SPEECH_MODEL',str(Path.home()/'.cache/infinite-creativity/whisper-base')))

def prepare_speech(path):
    from .model_download import install
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,digest in SPEECH_MODEL['files'].items():
        target=path/name
        install(SPEECH_MODEL['repo'],SPEECH_MODEL['revision'],name,target,digest)
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
            cache=ContentCache(directory,hosts=getattr(http,'hosts',()))
            container=a.get('containers',{}).get(f.get('container_id'))
            archive=cache.multipart_zip(container['parts']) if container and container['type']=='split-zip' else cache.remote_zip(f['url'])
            with archive as z:
                entry=z.getinfo(f['archive_entry'])
                if entry.file_size>max_bytes or entry.file_size>max(1,entry.compress_size)*500:raise ValueError('Archive member exceeds review budget')
                body=z.read(entry)
    else:body=http.read(f['url'],max_bytes)
    if f.get('sha') and not f.get('archive_entry'):
        if hashlib.sha1(('blob '+str(len(body))+'\0').encode()+body).hexdigest()!=f['sha']:raise ValueError('Original Git blob integrity mismatch during review')
        if body.startswith(b'version https://git-lfs.github.com/spec/v1') and f['url'].startswith('https://raw.githubusercontent.com/'):
            import re
            pointer=re.search(rb'\noid sha256:([0-9a-f]{64})\nsize (\d+)',body)
            if not pointer or int(pointer[2])>max_bytes:raise ValueError('Git LFS original exceeds review budget or has an invalid pointer')
            body=http.read(f['url'].replace('raw.githubusercontent.com/','media.githubusercontent.com/media/',1),max_bytes)
            if len(body)!=int(pointer[2]) or hashlib.sha256(body).hexdigest()!=pointer[1].decode():raise ValueError('Git LFS original integrity mismatch during review')
    if f.get('sha256') and hashlib.sha256(body).hexdigest()!=f['sha256']:raise ValueError('Original SHA256 mismatch during review')
    if f.get('md5') and hashlib.md5(body).hexdigest()!=f['md5']:raise ValueError('Original checksum mismatch during review')
    return body

class RequestScreener:
    """Reuse exact pixel-file verdicts only inside one geometry inspection."""
    def __init__(self,classifier):self.classifier=classifier;self.seen={}
    def image(self,path):
        digest=hashlib.sha256(Path(path).read_bytes()).digest()
        if digest not in self.seen:
            if len(self.seen)>=512:self.seen.pop(next(iter(self.seen)))
            self.seen[digest]=self.classifier.image(path)
        return self.seen[digest]

def image_check(image,classifier,directory,index):
    from PIL import Image
    if not isinstance(image,Image.Image):raise ValueError('Invalid decoded image')
    if image.width*image.height>limits()['pixels']:raise ValueError('Decoded image exceeds pixel budget')
    # Retain a full-image view plus every tile for high-resolution originals.
    views=[image]
    if image.width*image.height>40000000:
        views=[image.copy()];views[0].thumbnail((4096,4096))
        views.extend(image.crop((x,y,min(x+4096,image.width),min(y+4096,image.height))) for y in range(0,image.height,4096) for x in range(0,image.width,4096))
    risks=[]
    path=Path(directory)/('view-'+str(index)+'.png')
    try:
        for view in views:
            view.save(path);verdict=classifier.image(path)
            if verdict['state']!='preview-screened':raise ValueError('Original media sexual/suggestive classifier risk')
            risks.append(float(verdict.get('risk_probability',0)))
    finally:path.unlink(missing_ok=True)
    return max(risks)

def review_audio(body):
    import av
    import numpy as np
    from av.audio.resampler import AudioResampler
    frames=[];count=0;resampler=AudioResampler(format='fltp',layout='mono',rate=16000)
    with av.open(media_input(body)) as container:
        if not container.streams.audio:raise ValueError('Original has no audio stream')
        source_stream=container.streams.audio[0];source_audio={'sample_rate':source_stream.codec_context.sample_rate,'channels':len(source_stream.codec_context.layout.channels),'bit_rate':source_stream.bit_rate,'codec':source_stream.codec_context.name}
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                block=converted.to_ndarray().reshape(-1);count+=len(block)
                if count>16000*limits()['audio_seconds']:raise ValueError('Audio exceeds complete review duration budget')
                frames.append(block)
        for converted in resampler.resample(None):frames.append(converted.to_ndarray().reshape(-1))
    samples=np.concatenate(frames) if frames else np.array([],dtype=np.float32)
    if not len(samples) or not np.isfinite(samples).all():raise ValueError('Empty or invalid decoded audio')
    rms=float(np.sqrt(np.mean(samples*samples)));clipping=float(np.mean(np.abs(samples)>=.9999))
    if rms<1e-7 or clipping>.08:raise ValueError('Silent or severely clipped audio')
    segments,info=speech_model(str(speech_path())).transcribe(samples,task='translate',beam_size=1,condition_on_previous_text=False,vad_filter=True)
    transcript=[];started=time.monotonic()
    for segment in segments:
        if time.monotonic()-started>limits()['cpu_seconds']:raise ValueError('Full speech review exceeded CPU budget')
        if not acceptable(segment.text) or review_terms(segment.text):raise ValueError('Audio speech sexual/suggestive content policy')
        transcript.append(segment.text)
        progress(getattr(segment,'end',len(samples)/16000), len(samples)/16000,'Reviewing original audio speech')
    return {'scope':'entire decoded audio and multilingual speech translated to English; lexical sexual/suggestive screening','duration':len(samples)/16000,
            'speech_segments':len(transcript),'language':info.language,'rms':rms,'clipping_fraction':clipping,'original_audio':source_audio,'model_revision':SPEECH_MODEL['revision'],
            'limits':'Speech recognition can miss words, music lyrics and nonverbal contextual innuendo; no transcript is retained or returned.'}

def audio_excerpt(path,start=0,seconds=12):
    """Bounded native MCP listening excerpt from an already authorized original."""
    import math,wave,av
    import numpy as np
    if isinstance(start,bool) or isinstance(seconds,bool) or not isinstance(start,(int,float)) or not isinstance(seconds,(int,float)) or not math.isfinite(start) or not math.isfinite(seconds) or not 0<=start<=1800 or not 0<seconds<=30:raise ValueError('Choose a finite excerpt start 0..1800 seconds and duration >0..30')
    rate=22050;begin=int(start*rate);end=begin+int(seconds*rate);position=0;parts=[]
    resampler=av.audio.resampler.AudioResampler(format='fltp',layout='mono',rate=rate)
    with av.open(str(path)) as container:
        if not container.streams.audio:raise ValueError('Original has no audio stream')
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                block=converted.to_ndarray().reshape(-1);stop=position+len(block)
                if stop>begin and position<end:parts.append(block[max(0,begin-position):min(len(block),end-position)].copy())
                position=stop
            if position>=end:break
            progress(position/rate,start+seconds,'Preparing current bounded audio listening excerpt')
        if position<end:
            for converted in resampler.resample(None):
                block=converted.to_ndarray().reshape(-1);stop=position+len(block)
                if stop>begin and position<end:parts.append(block[max(0,begin-position):min(len(block),end-position)].copy())
                position=stop
    samples=np.concatenate(parts) if parts else np.array([],dtype=np.float32)
    if not len(samples) or not np.isfinite(samples).all():raise ValueError('Requested excerpt is empty or invalid')
    output=io.BytesIO()
    with wave.open(output,'wb') as writer:writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(rate);writer.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
    return output.getvalue(),{'start_seconds':start,'duration_seconds':len(samples)/rate,'sample_rate':rate,'channels':1,'scope':'Listening excerpt only. Production original bytes, resolution and channels remain unchanged; the full original must have passed its delivery guard.'}

def review_frames(body,extension,classifier,directory):
    from PIL import Image
    risks=[];frames=0
    if extension in {'gif','webp','apng','png'}:
        with Image.open(media_input(body)) as im:
            total=getattr(im,'n_frames',1)
            if total>limits()['frames']:raise ValueError('Animation exceeds full-frame review budget')
            for i in range(total):
                im.seek(i);risks.append(image_check(im.convert('RGBA'),classifier,directory,i));frames+=1;progress(frames,total,'Reviewing every original animation frame')
        audio=None
    else:
        import av
        with av.open(media_input(body)) as container:
            if not container.streams.video:raise ValueError('Original has no video stream')
            has_audio=bool(container.streams.audio)
            for frame in container.decode(video=0):
                if frames>=limits()['frames']:raise ValueError('Video exceeds full-frame review budget')
                risks.append(image_check(frame.to_image(),classifier,directory,frames));frames+=1
                progress(frames,container.streams.video[0].frames or limits()['frames'],'Reviewing every decoded video frame')
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
    from .meshopt_review import decode_glb
    body=decode_glb(body)
    classifier=RequestScreener(classifier)
    import numpy as np
    import trimesh
    from PIL import Image,ImageDraw
    import struct
    if len(body)<20 or body[:4]!=b'glTF':raise ValueError('Invalid original GLB')
    version,total,length,kind=struct.unpack_from('<IIII',body,4)
    if version!=2 or total!=len(body) or kind!=0x4E4F534A or length>16*1024*1024 or 20+length>len(body):raise ValueError('Invalid original GLB JSON chunk')
    document=json.loads(body[20:20+length])
    if any(v.get('uri') for v in document.get('buffers',[])) or any(v.get('uri') and not v['uri'].startswith('data:') for v in document.get('images',[])):raise ValueError('External model dependencies require scoped review')
    scene=trimesh.load(io.BytesIO(body),file_type='glb',force='scene',process=False)
    risks=[];triangles=0;texture_count=0
    # Inspect all stored image bytes, including unused/normal/occlusion maps.
    # Material conversion alone can silently omit those original images.
    offset=20+length;binary=b''
    while offset+8<=len(body):
        size,chunk=struct.unpack_from('<II',body,offset);offset+=8
        if offset+size>len(body):raise ValueError('Invalid GLB binary extent')
        if chunk==0x004E4942:binary=body[offset:offset+size]
        offset+=size
    for entry in document.get('images',[]):
        if 'bufferView' in entry:
            view=document['bufferViews'][entry['bufferView']];start=view.get('byteOffset',0);end=start+view['byteLength']
            if view.get('buffer',0)!=0 or not 0<=start<end<=len(binary):raise ValueError('Embedded image exceeds GLB buffer bounds')
            pixels=binary[start:end]
        elif entry.get('uri','').startswith('data:'):
            import base64
            header,payload=entry['uri'].split(',',1)
            if ';base64' not in header:raise ValueError('Unsupported embedded texture encoding')
            pixels=base64.b64decode(payload,validate=True)
        else:raise ValueError('Original embedded texture is missing')
        with Image.open(io.BytesIO(pixels)) as image:risks.append(image_check(image.convert('RGBA'),classifier,directory,'embedded-'+str(texture_count)))
        texture_count+=1
    for geometry in scene.geometry.values():
        if not hasattr(geometry,'vertices') or not hasattr(geometry,'faces'):raise ValueError('Non-triangle geometry requires a different reviewer')
        if not np.isfinite(geometry.vertices).all():raise ValueError('Non-finite original geometry')
        triangles+=len(geometry.faces)
        if triangles>limits()['triangles']:raise ValueError('Geometry exceeds full rendering budget')
    instanced=sum(len(scene.geometry[name].faces) for node in scene.graph.nodes_geometry for _,name in [scene.graph[node]])
    if instanced>limits()['triangles']:raise ValueError('Instanced geometry exceeds rendering budget')
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
        for n,face_index in enumerate(order):
            if n%10000==0:progress(n,len(order),'Rendering complete model views')
            polygon=[tuple(v) for v in (points[faces[face_index],:2]*330+192)]
            draw.polygon(polygon,fill=tuple(int(v) for v in colors[face_index,:3]))
        risks.append(image_check(im,classifier,directory,texture_count+i))
    pose_count=0
    if document.get('animations') or any(p.get('targets') for mesh in document.get('meshes',[]) for p in mesh.get('primitives',[])):
        from .gltf_review import poses
        for vertices,faces,colors,clip,timestamp in poses(body):
            if len(faces)>limits()['triangles']:raise ValueError('Animated geometry exceeds rendering budget')
            vertices=(vertices-(vertices.min(axis=0)+vertices.max(axis=0))/2)/max(float(np.ptp(vertices,axis=0).max()),1e-9)
            for axis in [(0,1,2),(1,2,0)]:
                points=vertices[:,axis].copy();points[:,1]*=-1;im=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(im)
                for n,face_index in enumerate(np.argsort(points[faces,2].mean(axis=1))):
                    if n%10000==0:progress(n,len(faces),'Rendering animation pose geometry')
                    draw.polygon([tuple(v) for v in points[faces[face_index],:2]*330+192],fill=tuple(int(np.clip(v,0,255)) for v in colors[face_index,:3]))
                risks.append(image_check(im,classifier,directory,texture_count+6+pose_count*2+axis[0]))
            pose_count+=1
            progress(pose_count,limits()['poses'],'Reviewing original animation poses')
    return {'scope':'self-contained original GLB, embedded textures, six static views'+(' and declared keyframe/midpoint skin/morph poses' if pose_count else ''),'triangles':triangles,'textures':texture_count,'rendered_views':6+pose_count*2,'animation_poses':pose_count,'maximum_risk':max(risks),'limits':'Discrete orthographic views can miss occluded detail, unanimated morph combinations or intermediate motion. External dependencies and files above bounded pose budgets are withheld.'}

def review_original(http,a,classifier):
    supported={'wav','ogg','mp3','flac','m4a','gif','webp','apng','mp4','webm','mov','svg','glb','exr','hdr'}
    files=[v for v in a.get('files',[]) if v.get('role') in {'main','variant'} and Path(v.get('filename','')).suffix.lstrip('.').lower() in supported]
    if not files:return None
    # Review the selected deliverable type. Variants remain declared; callers
    # receive only files whose bytes are re-reviewed at delivery.
    f=min(files,key=lambda v:v.get('bytes') or 12*1024*1024);ext=Path(f['filename']).suffix.lstrip('.').lower()
    body=original_bytes(http,a,f)
    from .request_scope import CURRENT
    if CURRENT.get() is not None:
        from .media_process import execute
        with tempfile.TemporaryDirectory(prefix='infinite-creativity-original-worker-') as directory:
            path=Path(directory)/('original.'+ext);path.write_bytes(body)
            return execute('original',path,directory,extension=ext,asset=a)
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-original-review-') as directory,profile('fast'):
        if ext in {'wav','ogg','mp3','flac','m4a'}:result=review_audio(body)
        elif ext=='svg':result=review_vector(body,classifier,directory)
        elif ext=='glb':result=review_geometry(body,classifier,directory)
        else:result=review_frames(body,ext,classifier,directory)
        progress(1,1,'Completed bounded current original review')
    if ext=='glb':
        from .meshopt_review import decode_glb
        import struct
        expanded=decode_glb(body);length=struct.unpack_from('<I',expanded,12)[0];document=json.loads(expanded[20:20+length])
        if isinstance(document.get('asset'),dict):document['asset'].pop('generator',None)
        fingerprint=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode());fingerprint.update(expanded[20+length:])
        result['structured_content_sha256']=fingerprint.hexdigest()
        result['structured_dedup_scope']='GLB JSON formatting/generator normalized; complete binary chunks and geometry/material/animation declarations preserved. Not a near-shape similarity guarantee.'
    return {'state':'original-media-screened','scope':result['scope'],'evidence':result,'sha256':hashlib.sha256(body).hexdigest(),
            'file_identity':f.get('archive_entry') or f['url'],'checks':['sexual','suggestive','technical-quality'],'quality':{'state':'decoded-and-structurally-valid','limits':'No subjective aesthetic quality certification; intentional minimal/pixel/low-poly styles are preserved.'}}


def check_delivery(a,file,path):
    """Recheck the exact selected bytes, including an alternate variant."""
    if os.environ.get('IC_SAFETY_MODE','strict')!='strict':return
    from .live_admission import screener,model_path
    from .library import TEXT_FORMATS
    receipt=a.get('_review_files',{}).get(file.get('_review_key'))
    if receipt:
        with Path(path).open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=receipt['sha256'] or Path(path).stat().st_size!=receipt['bytes']:raise ValueError('Original changed since selected review; run review_asset_media again')
        return
    from .request_scope import CURRENT
    if CURRENT.get() is not None and not a.get('software_only') and file.get('role') not in {'license','provenance'}:
        from .media_process import execute
        execute('delivery',path,Path(path).parent,asset=a,file=file)
        return
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
    from .meshopt_review import decode_glb
    body=decode_glb(body)
    import numpy as np
    import trimesh
    from PIL import Image,ImageDraw
    mesh=trimesh.load(io.BytesIO(body),file_type='glb',force='scene',process=False).to_mesh()
    if len(mesh.faces)>limits()['triangles']:raise ValueError('Preview geometry exceeds rendering budget')
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
