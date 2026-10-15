"""Offline audit of the explicit reconstructed flame transforms across original idle frames."""
import hashlib,json,math,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def glb(path):
 raw=path.read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);binary=raw[28+n:]
 def accessor(index):
  a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
  if a['componentType']!=5126 or 'byteStride' in v:raise ValueError('Unexpected audit accessor')
  return np.frombuffer(binary,dtype='<f4',count=a['count']*width,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape((-1,width)).astype(float)
 return doc,accessor,hashlib.sha256(raw).hexdigest()
def trs(t,q,s):
 x,y,z,w=q;m=np.eye(4);m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(s);m[:3,3]=t;return m
def main():
 base=ROOT/'analysis/characters/shiranui';p=base/'effects/render-inputs'
 attachment=json.loads((p/'attachment.json').read_text('utf8'))
 doc,acc,weapon_hash=glb(base/'export-weapon/shiranuiweapon-idle.colour-reference.glb')
 fd,fa,flame_hash=glb(p/'flame-01.glb')
 if len(fd['meshes'])!=1 or len(fd['meshes'][0]['primitives'])!=1 or len(fd['nodes'])!=1 or any(k in fd['nodes'][0] for k in ('matrix','translation','rotation','scale')):raise ValueError('New geometry layout requires expanded audit')
 vertices=fa(fd['meshes'][0]['primitives'][0]['attributes']['POSITION']);vertices=np.column_stack((vertices,np.ones(len(vertices))))
 anim=doc['animations'][0];times=acc(anim['samplers'][0]['input'])[:,0];channels=[]
 for c in anim['channels']:
  sampler=anim['samplers'][c['sampler']]
  if not np.array_equal(acc(sampler['input'])[:,0],times):raise ValueError('Unequal channel sample times')
  channels.append((c['target']['node'],c['target']['path'],acc(sampler['output'])))
 parent={c:i for i,n in enumerate(doc['nodes']) for c in n.get('children',[])}
 named={n['name']:i for i,n in enumerate(doc['nodes'])}
 def layers(n,m=None):
  m=np.eye(4) if m is None else m
  q=[0,0,0,1]
  if 'forward' in n:
   axis=np.array(n['forward'][:3]);axis/=np.linalg.norm(axis);angle=math.radians(n['forward'][3])/2;q=[*(axis*math.sin(angle)),math.cos(angle)]
  m=m@trs(n['position'],q,n['scale'])
  if n['tag']=='Model':yield n,m@np.diag([n.get('model_scale',1)]*3+[1])
  for c in n['children']:yield from layers(c,m)
 sockets=[]
 for s in attachment['sockets']:
  matrix=np.array(s['matrix']).reshape((4,4),order='F')
  if not np.allclose(matrix[3],[0,0,0,1]):raise ValueError('Nonaffine socket')
  sockets.append((s,matrix,list(layers(attachment['effects'][s['effect']]))))
 bounds=[];origins=[]
 for frame in range(len(times)):
  props=[dict(translation=n.get('translation',[0,0,0]),rotation=n.get('rotation',[0,0,0,1]),scale=n.get('scale',[1,1,1])) for n in doc['nodes']]
  for index,kind,values in channels:props[index][kind]=values[frame]
  local=[np.array(n['matrix']).reshape((4,4),order='F') if 'matrix' in n else trs(v['translation'],v['rotation'],v['scale']) for n,v in zip(doc['nodes'],props)]
  worlds={}
  def world(i):
   if i not in worlds:worlds[i]=(world(parent[i]) if i in parent else np.eye(4))@local[i]
   return worlds[i]
  framepoints=[];frameorigins=[]
  for socket,matrix,ls in sockets:
   wm=world(named[socket['bone']])@matrix;frameorigins.append(wm[:3,3].tolist())
   for node,lm in ls:framepoints.append((wm@lm@vertices.T).T[:,:3])
  points=np.concatenate(framepoints)
  if not np.isfinite(points).all():raise ValueError('Nonfinite transformed geometry')
  bounds.append(dict(min=points.min(0).tolist(),max=points.max(0).tolist()));origins.append(frameorigins)
 report=dict(weapon_sha256=weapon_hash,flame_sha256=flame_hash,frames=len(times),sockets=len(sockets),instances_per_frame=sum(len(ls) for _,_,ls in sockets),all_vertices_finite=True,
  socket_diagnostics=[dict(name=s['name'],determinant=float(np.linalg.det(m[:3,:3])),orthogonality_error=float(np.max(np.abs(m[:3,:3].T@m[:3,:3]-np.eye(3)))),translation=m[:3,3].tolist()) for s,m,_ in sockets],
  first_frame_socket_origins=origins[0],last_frame_socket_origins=origins[-1],first_frame_bounds=bounds[0],all_frame_bounds=dict(min=np.min([b['min'] for b in bounds],0).tolist(),max=np.max([b['max'] for b in bounds],0).tolist()),
  transparent_orders=[dict(socket=s['name'],name=n['attributes']['Name'],order=int(n['attributes']['RenderOrder'])+int(n['attributes']['RenderBias']),mode=n['attributes']['TransparentMode']) for s,_,ls in sockets for n,_ in ls],
  conclusions=['Socket is parented to animated named bone; animated bone world times socket local times SFX local. No inverse bind matrix belongs in this attachment transform.',
   'Source export preserves XYZ coordinates; current socket column-major interpretation agrees with translation in final four matrix entries and is affine.',
   'Axis-angle Forward, constant ScaleFrame multiplication, native render-bias semantics remain unproven; finite bounds do not prove original visual equivalence.',
   'Alpha colour layers use renderOrder 0; additive layers 1. Equal-order items receive Three camera-depth sorting, not a proven original layer ordering.'],
  assumptions=attachment['assumptions'])
 (base/'effects/attachment-transform-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
 print(json.dumps({k:report[k] for k in ['frames','sockets','instances_per_frame','all_vertices_finite','all_frame_bounds']}))
if __name__=='__main__':main()
