"""Real local decoders/models on generated fixtures; no remote asset retained."""
import hashlib
import json
import math
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from infinite_creativity.media_process import execute,environment
from infinite_creativity.request_scope import CURRENT,RequestScope
from infinite_creativity.review_limits import profile
from infinite_creativity.specialized_media import blender_path


def verify():
    failures=0
    with tempfile.TemporaryDirectory(prefix='infinite-creativity-real-media-') as directory:
        root=Path(directory)
        from PIL import Image,ImageDraw
        image=Image.new('RGB',(256,256),'white');draw=ImageDraw.Draw(image);draw.rectangle((48,48,208,208),fill='#2463c6');image.save(root/'minimal.png')
        with wave.open(str(root/'tone.wav'),'wb') as sound:
            sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(16000)
            sound.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*440*i/16000))) for i in range(16000)))
        import trimesh
        mesh=trimesh.creation.box();mesh.visual.face_colors=[48,98,180,255];(root/'box.glb').write_bytes(mesh.export(file_type='glb'))
        cases=[('image','minimal.png','png'),('review','tone.wav','wav'),('review','box.glb','glb')]
        executable=blender_path()
        if executable:
            script=root/'create_fixture.py'
            script.write_text("import bpy,sys\nfrom pathlib import Path\nbpy.ops.wm.read_factory_settings(use_empty=True)\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.name='synthetic-review-box'\nbpy.ops.wm.save_as_mainfile(filepath=str(Path(sys.argv[-1])/'box.blend'))\n",encoding='utf-8')
            process=subprocess.run([executable,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--',str(root)],cwd=root,env=environment(root),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
            if process.returncode:raise ValueError('Blender could not create the controlled fixture')
            cases.append(('review','box.blend','blend'))
        for action,name,extension in cases:
            started=time.monotonic();token=CURRENT.set(RequestScope(seconds=330))
            try:
                with profile('extended'):
                    result=execute(action,root/name,root,extension=extension)
                if action=='image' and result.get('state')!='preview-screened':raise ValueError('Generated fixture not admitted: '+str(result.get('state')))
                if not result.get('decoder_isolation'):raise ValueError('No OS worker evidence')
                print(json.dumps({'case':name,'status':'passed','seconds':round(time.monotonic()-started,3),'scope':result.get('scope'),'worker':result['decoder_isolation'],'source_bytes':(root/name).stat().st_size}),flush=True)
            except Exception as error:
                failures+=1;print(json.dumps({'case':name,'status':'failed-or-withheld','seconds':round(time.monotonic()-started,3),'reason':str(error)[:300]}),flush=True)
            finally:CURRENT.reset(token)
    return failures


if __name__=='__main__':raise SystemExit(1 if verify() else 0)
