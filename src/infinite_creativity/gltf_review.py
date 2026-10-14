"""Bounded GLB animation pose evaluation for local visual screening.

Evaluates every declared keyframe time and interval midpoint, with skinning.
Does not claim that discrete views prove every continuously interpolated pose.
"""
import json,struct
from .review_limits import limits

def poses(body):
    import numpy as np
    if len(body)<20 or body[:4]!=b'glTF':raise ValueError('Invalid GLB')
    version,total=struct.unpack_from('<II',body,4)
    if version!=2 or total!=len(body):raise ValueError('Invalid GLB extent')
    offset=12;doc=None;binary=b''
    while offset+8<=len(body):
        size,kind=struct.unpack_from('<II',body,offset);offset+=8
        if offset+size>len(body):raise ValueError('Invalid GLB chunk extent')
        block=body[offset:offset+size];offset+=size
        if kind==0x4E4F534A:doc=json.loads(block)
        elif kind==0x004E4942:binary=block
    if doc is None:raise ValueError('GLB has no document')
    if any(b.get('uri') for b in doc.get('buffers',[])):raise ValueError('External animation buffers require separate review')
    component={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'};length={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
    cache={}
    def accessor(index):
        if index in cache:return cache[index]
        a=doc['accessors'][index]
        count=a['count'];cols=length[a['type']];dtype=np.dtype(component[a['componentType']])
        if not 0<count<=max(1000000,limits()['triangles']*3):raise ValueError('Animation accessor exceeds count budget')
        def read(view_index,offset,count,cols,dtype):
            view=doc['bufferViews'][view_index]
            if view.get('buffer',0)!=0:raise ValueError('External buffer unsupported')
            stride=view.get('byteStride',cols*dtype.itemsize);start=view.get('byteOffset',0)+offset
            if offset<0 or stride<cols*dtype.itemsize or start+(count-1)*stride+cols*dtype.itemsize>min(len(binary),view.get('byteOffset',0)+view['byteLength']):raise ValueError('Animation accessor exceeds bounds')
            return np.ndarray((count,cols),dtype=dtype,buffer=binary,offset=start,strides=(stride,dtype.itemsize)).astype(float)
        values=read(a['bufferView'],a.get('byteOffset',0),count,cols,dtype) if 'bufferView' in a else np.zeros((count,cols))
        if a.get('sparse'):
            sparse=a['sparse'];n=sparse['count'];indices=sparse['indices'];delta=sparse['values']
            if not 0<n<=count or indices['componentType'] not in {5121,5123,5125}:raise ValueError('Invalid sparse accessor count/index type')
            selected=read(indices['bufferView'],indices.get('byteOffset',0),n,1,np.dtype(component[indices['componentType']])).ravel().astype(int)
            if selected.min()<0 or selected.max()>=count or len(selected)>1 and not np.all(np.diff(selected)>0):raise ValueError('Invalid sparse accessor indices')
            values[selected]=read(delta['bufferView'],delta.get('byteOffset',0),n,cols,dtype)
        if a.get('normalized'):
            if dtype.kind=='u':values/=np.iinfo(dtype).max
            elif dtype.kind=='i':values=np.maximum(values/np.iinfo(dtype).max,-1)
        if not np.isfinite(values).all():raise ValueError('Non-finite original animation values')
        cache[index]=values;return values
    def trs(node,updates):
        if 'matrix' in node:return np.asarray(node['matrix']).reshape(4,4).T
        t=np.asarray(updates.get('translation',node.get('translation',[0,0,0])));s=np.asarray(updates.get('scale',node.get('scale',[1,1,1])));q=np.asarray(updates.get('rotation',node.get('rotation',[0,0,0,1])))
        q=q/max(np.linalg.norm(q),1e-12);x,y,z,w=q
        matrix=np.eye(4);matrix[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(s);matrix[:3,3]=t;return matrix
    nodes=doc.get('nodes',[]);parents={c:i for i,n in enumerate(nodes) for c in n.get('children',[])}
    total_views=0
    animations=doc.get('animations',[]) or [{'name':'static morph defaults','samplers':[],'channels':[]}]
    for animation in animations:
        times=sorted({float(t) for sampler in animation['samplers'] for t in accessor(sampler['input'])[:,0]})
        times=sorted(set(times+[float((a+b)/2) for a,b in zip(times,times[1:])]))
        if not times:times=[0.0]
        total_views+=len(times)
        if total_views>limits()['poses']:raise ValueError('Animation exceeds complete keyframe/midpoint review budget; choose a smaller clip file')
        for timestamp in times:
            changes={}
            for channel in animation['channels']:
                target=channel['target'];path=target['path'];sampler=animation['samplers'][channel['sampler']]
                ts=accessor(sampler['input'])[:,0];values=accessor(sampler['output']);i=max(0,min(len(ts)-1,int(np.searchsorted(ts,timestamp,side='right')-1)));j=min(len(ts)-1,i+1)
                interpolation=sampler.get('interpolation','LINEAR')
                if not np.all(np.diff(ts)>0):raise ValueError('Animation times must strictly increase')
                if path=='weights':
                    mesh=doc['meshes'][nodes[target['node']]['mesh']];width=len(mesh['primitives'][0].get('targets',[]))
                    if not width:raise ValueError('Morph animation has no targets')
                    values=values.reshape(len(ts)*(3 if interpolation=='CUBICSPLINE' else 1),width)
                fraction=0 if sampler.get('interpolation')=='STEP' or ts[j]==ts[i] else float(np.clip((timestamp-ts[i])/(ts[j]-ts[i]),0,1))
                if interpolation=='CUBICSPLINE':
                    left,right=values[i*3+1],values[j*3+1];f=fraction;dt=float(ts[j]-ts[i])
                    value=(2*f**3-3*f**2+1)*left+(f**3-2*f**2+f)*dt*values[i*3+2]+(-2*f**3+3*f**2)*right+(f**3-f**2)*dt*values[j*3]
                    if path=='rotation':value=value/max(float(np.linalg.norm(value)),1e-12)
                    changes.setdefault(target['node'],{})[path]=value;continue
                if interpolation not in {'LINEAR','STEP'}:raise ValueError('Unknown animation interpolation')
                left=values[i];right=values[j]
                if path=='rotation' and np.dot(left,right)<0:right=-right
                value=left*(1-fraction)+right*fraction
                if path=='rotation':
                    dot=float(np.clip(np.dot(left,right),-1,1));theta=float(np.arccos(dot))
                    if abs(np.sin(theta))>1e-6:value=(np.sin((1-fraction)*theta)*left+np.sin(fraction*theta)*right)/np.sin(theta)
                changes.setdefault(target['node'],{})[path]=value
            worlds={};visiting=set()
            def world(index):
                if index in worlds:return worlds[index]
                if index in visiting:raise ValueError('Cyclic animation graph')
                visiting.add(index);local=trs(nodes[index],changes.get(index,{}));m=world(parents[index])@local if index in parents else local;visiting.remove(index);worlds[index]=m;return m
            vertices=[];faces=[];colors=[]
            for index,node in enumerate(nodes):
                if 'mesh' not in node:continue
                for primitive in doc['meshes'][node['mesh']]['primitives']:
                    if primitive.get('mode',4)!=4:raise ValueError('Non-triangle geometry requires specialized review')
                    attributes=primitive['attributes'];positions=accessor(attributes['POSITION']).copy()
                    targets=primitive.get('targets',[])
                    weights=changes.get(index,{}).get('weights',node.get('weights',doc['meshes'][node['mesh']].get('weights',[0]*len(targets))))
                    if len(weights)!=len(targets):raise ValueError('Morph weights do not match target count')
                    for weight,target in zip(weights,targets):
                        if 'POSITION' in target:positions+=float(weight)*accessor(target['POSITION'])
                    v=np.c_[positions,np.ones(len(positions))]
                    if 'skin' in node:
                        if 'JOINTS_0' not in attributes or 'WEIGHTS_0' not in attributes:raise ValueError('Unsupported skin influence layout')
                        skin=doc['skins'][node['skin']];inverse=accessor(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1) if 'inverseBindMatrices' in skin else np.tile(np.eye(4),(len(skin['joints']),1,1))
                        matrices=np.array([world(joint)@bind for joint,bind in zip(skin['joints'],inverse)]);joints=accessor(attributes['JOINTS_0']).astype(int);weights=accessor(attributes['WEIGHTS_0'])
                        if 'JOINTS_1' in attributes:
                            if 'WEIGHTS_1' not in attributes:raise ValueError('Missing additional skin weights')
                            joints=np.concatenate([joints,accessor(attributes['JOINTS_1']).astype(int)],axis=1);weights=np.concatenate([weights,accessor(attributes['WEIGHTS_1'])],axis=1)
                        if joints.min()<0 or joints.max()>=len(matrices) or not np.allclose(weights.sum(axis=1),1,atol=.025):raise ValueError('Invalid skin weights or joint indices')
                        transformed=sum(np.einsum('nij,nj->ni',matrices[joints[:,k]],v)*weights[:,k,None] for k in range(joints.shape[1]))[:,:3]
                    else:transformed=(v@world(index).T)[:,:3]
                    indices=accessor(primitive['indices']).astype(int).ravel() if 'indices' in primitive else np.arange(len(v))
                    if len(indices)%3 or indices.min()<0 or indices.max()>=len(v):raise ValueError('Invalid animation mesh indices')
                    f=indices.reshape(-1,3);faces.append(f+sum(len(x) for x in vertices));vertices.append(transformed)
                    material=doc.get('materials',[])[primitive['material']] if 'material' in primitive else {};color=material.get('pbrMetallicRoughness',{}).get('baseColorFactor',[.7,.7,.7,1]);colors.append(np.tile(np.array(color)*255,(len(f),1)))
            if not vertices:raise ValueError('Animation has no rendered mesh')
            yield np.concatenate(vertices),np.concatenate(faces),np.concatenate(colors),animation.get('name','unnamed'),timestamp
