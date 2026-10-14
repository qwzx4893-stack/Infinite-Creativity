"""Fixed headless Blender reader; this software never runs asset text scripts."""
import json,sys,os
from pathlib import Path
import bpy

def main():
    configuration=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    path=Path(configuration['input']);output=Path(configuration['output']);budget=configuration['limits'];extension=path.suffix.lower()
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if extension=='.blend':bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
    elif extension in {'.glb','.gltf'}:bpy.ops.import_scene.gltf(filepath=str(path))
    elif extension=='.fbx':
        try:bpy.ops.import_scene.fbx.get_rna_type();classic=True
        except Exception:classic=False
        if classic:bpy.ops.import_scene.fbx(filepath=str(path),use_image_search=False)
        else:bpy.ops.wm.fbx_import(filepath=str(path))
    elif extension=='.obj':bpy.ops.wm.obj_import(filepath=str(path))
    elif extension in {'.usd','.usda','.usdc','.usdz'}:bpy.ops.wm.usd_import(filepath=str(path),import_textures_mode='IMPORT_PACK',import_visible_only=False,set_frame_range=True)
    elif extension=='.abc':bpy.ops.wm.alembic_import(filepath=str(path),as_background_job=False)
    elif extension=='.dae':bpy.ops.wm.collada_import(filepath=str(path))
    elif extension=='.bvh':bpy.ops.import_anim.bvh(filepath=str(path))
    else:raise ValueError('Unsupported native format')
    if bpy.data.libraries:raise ValueError('External linked native libraries are not authorized by this original scope')
    if len(bpy.data.sounds) or len(bpy.data.movieclips) or any(s.sequence_editor and len(s.sequence_editor.strips) for s in bpy.data.scenes):raise ValueError('Native embedded audio/video/sequencer requires separate full media review')
    if any(m.type in {'MESH_SEQUENCE_CACHE','FLUID','OCEAN'} for o in bpy.data.objects for m in o.modifiers):raise ValueError('Time-varying geometry/cache/simulation needs complete native frame review')
    cached=[o for o in bpy.data.objects if any(c.type=='TRANSFORM_CACHE' for c in o.constraints)]
    if cached:
        frames=range(bpy.context.scene.frame_start,bpy.context.scene.frame_end+1)
        if len(frames)*2-1>budget['poses']:raise ValueError('Native transform-cache animation exceeds complete pose budget')
        samples=[]
        for frame in frames:
            bpy.context.scene.frame_set(frame)
            samples.append((frame,[(o.parent.matrix_world.inverted()@o.matrix_world if o.parent else o.matrix_world).copy() for o in cached]))
        for obj in cached:
            for c in list(obj.constraints):
                if c.type=='TRANSFORM_CACHE':obj.constraints.remove(c)
        for frame,matrices in samples:
            for obj,matrix in zip(cached,matrices):
                obj.rotation_mode='QUATERNION';obj.location,obj.rotation_quaternion,obj.scale=matrix.decompose()
                for field in ('location','rotation_quaternion','scale'):obj.keyframe_insert(data_path=field,frame=frame)
        bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    root=Path(configuration['staging_root']).resolve();packed=0
    for image in list(bpy.data.images):
        if image.source not in {'FILE','GENERATED'}:raise ValueError('Temporal or unsupported native image sources need separate review')
        if image.source=='FILE' and not image.packed_file:
            source=Path(bpy.path.abspath(image.filepath)).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                name=Path(image.filepath.replace('\\','/')).name
                candidates=[v for v in root.rglob(name) if v.is_file()]
                if len(candidates)!=1:raise ValueError('Native texture is missing/ambiguous in explicitly staged originals')
                image.filepath=str(candidates[0]);image.reload()
        if image.size[0]*image.size[1]>budget['pixels']:raise ValueError('Native texture exceeds pixel budget')
        if image.size[0]>0:
            image.save_render(str(output/('texture-'+str(packed)+'.png')));packed+=1
            if packed>budget['layers']:raise ValueError('Native texture count exceeds review budget')
    # Hidden mesh data is included rather than silently omitted by export.
    for mesh in bpy.data.meshes:
        if mesh.users==0:bpy.context.scene.collection.objects.link(bpy.data.objects.new('review-unused-mesh',mesh))
    skeleton_proxy=False
    if extension=='.bvh':
        # Skeleton-only motion has no surface mesh. Add a labelled bone proxy
        # for pose review; original BVH bytes remain the deliverable.
        for armature in list(bpy.data.objects):
            if armature.type!='ARMATURE':continue
            vertices=[];faces=[];groups=[]
            for bone in armature.data.bones:
                start=len(vertices);head=bone.head_local;tail=bone.tail_local;radius=max(bone.length*.06,.005)
                for point in (head,tail):
                    for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]:vertices.append(tuple(point+__import__('mathutils').Vector((x*radius,y*radius,0))))
                faces.extend(tuple(start+i for i in face) for face in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
                groups.append((bone.name,list(range(start,start+8))))
            mesh=bpy.data.meshes.new('review-bone-proxy');mesh.from_pydata(vertices,[],faces);obj=bpy.data.objects.new('review-bone-proxy',mesh);bpy.context.scene.collection.objects.link(obj)
            for name,indices in groups:obj.vertex_groups.new(name=name).add(indices,1,'REPLACE')
            obj.parent=armature;modifier=obj.modifiers.new('review-skeleton','ARMATURE');modifier.object=armature;skeleton_proxy=True
    objects=list(bpy.data.objects)
    if len(objects)>10000:raise ValueError('Native scene exceeds object budget')
    for obj in objects:
        if obj.type not in {'MESH','ARMATURE','EMPTY','LIGHT','CAMERA','CURVE','FONT'}:raise ValueError('Native volumes/simulation or unsupported object types require specialized review')
        obj.hide_render=False;obj.hide_viewport=False
        if obj.name not in bpy.context.scene.objects:bpy.context.scene.collection.objects.link(obj)
    for obj in objects:
        if obj.type in {'CURVE','FONT'}:
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target='MESH')
    triangles=sum(sum(max(0,len(p.vertices)-2) for p in obj.data.polygons) for obj in objects if obj.type=='MESH')
    if triangles>budget['triangles']:raise ValueError('Native scene exceeds triangle review budget')
    report={'reader':'Blender '+bpy.app.version_string,'source_format':extension.lstrip('.'),'meshes':len(bpy.data.meshes),'objects':len(objects),'triangles_before_evaluation':triangles,'armatures':len(bpy.data.armatures),'bones':sum(len(v.bones) for v in bpy.data.armatures),'actions':len(bpy.data.actions),'baked_transform_cache_objects':len(cached),'skeleton_proxy':skeleton_proxy,'names':[v.name for collection in (bpy.data.objects,bpy.data.materials,bpy.data.actions) for v in collection]+[bone.name for armature in bpy.data.armatures for bone in armature.bones],'packed_or_staged_textures':packed,'scripts_executed':False,'limits':'Converted meshes/materials/animations only; external libraries, simulation/volumes and unsupported object types are withheld. BVH uses generated bone proxies, not a character surface.'}
    bpy.ops.export_scene.gltf(filepath=str(output/'converted.glb'),export_format='GLB',use_selection=False,export_animations=True,export_apply=False)
    (output/'report.json').write_text(json.dumps(report),encoding='utf-8')

if __name__=='__main__':
    try:main()
    except Exception as error:
        try:
            configuration=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'));Path(configuration['output'],'report.json').write_text(json.dumps({'error':str(error)[:300]}),encoding='utf-8')
        finally:sys.exit(2)
