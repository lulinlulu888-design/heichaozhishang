"""Verify a local UE handoff without an Unreal editor or fabricated engine assets."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/unreal/import-inputs'
def digest(data):return hashlib.sha256(data).hexdigest()
def read_glb(data):
 if data[:4]!=b'glTF' or struct.unpack_from('<I',data,4)[0]!=2 or struct.unpack_from('<I',data,8)[0]!=len(data):raise ValueError('Invalid GLB envelope')
 size,kind=struct.unpack_from('<II',data,12)
 if kind!=0x4e4f534a or size>len(data)-20:raise ValueError('Invalid GLB JSON chunk')
 return json.loads(data[20:20+size])
def glb_summary(doc):
 primitives=[p for m in doc.get('meshes',[]) for p in m['primitives']]
 return dict(meshes=len(doc.get('meshes',[])),mesh_instances=sum('mesh' in n for n in doc.get('nodes',[])),
  vertices=sum(doc['accessors'][p['attributes']['POSITION']]['count'] for p in primitives),
  triangles=sum(doc['accessors'][p['indices']]['count']//3 for p in primitives),
  nodes=len(doc.get('nodes',[])),skins=len(doc.get('skins',[])),
  bones=[len(s['joints']) for s in doc.get('skins',[])],
  animations=[dict(name=a.get('name'),channels=len(a['channels'])) for a in doc.get('animations',[])],
  images=len(doc.get('images',[])),extensions=doc.get('extensionsUsed',[]))
def contained(root,relative):
 path=(root/relative).resolve()
 if not path.is_relative_to(root.resolve()):raise ValueError('Path escapes handoff root')
 return path

def verify():
 m=json.loads((BASE/'manifest.json').read_text('utf8'));assert m['schema']=='hczs-unreal-import-inputs-v1'
 ids=set();paths=set();rows=[]
 for a in m['assets']:
  assert a['id'] not in ids and a['file'] not in paths;ids.add(a['id']);paths.add(a['file'])
  source=contained(ROOT,a['source_file']);target=contained(BASE,a['file']);s=source.read_bytes();t=target.read_bytes()
  assert digest(s)==a['source_sha256']==a['sha256']==digest(t),'Source/copy hash mismatch: '+a['id']
  assert a['import_path'].startswith('/Game/Recovered/') and '..' not in a['import_path']
  if a['kind'].startswith('gltf_'):assert glb_summary(read_glb(t))==a['geometry']
  if a['id']=='elsa':
   doc=read_glb(t)
   assert a['character_id']==1 and a['source_lod']['row']==16 and a['source_lod']['level']==0
   assert a['source_lod']['model_path']=='character/player/ailisha/ailisha_yangcheng.gim'
   assert a['geometry']['vertices']==19063 and a['geometry']['triangles']==29240 and a['geometry']['bones']==[180]
   assert a['geometry']['animations']==[dict(name='home_stand_idle_1',channels=540)]
   assert a['animation_scope']['hall_animation_available'] is True
   assert a['animation_scope']['required_hall_clip']=='home_stand_idle_1'
   assert doc['extras']['animationSourceBaseGlbSha256']=='84956d9eeec1285c4de49faa6f0def6453663f288fb40352cf23deec6479a35f'
  if a['kind']=='texture':assert t[:8]==b'\x89PNG\r\n\x1a\n' and list(struct.unpack_from('>II',t,16))==a['dimensions']
  if a['kind']=='metadata':json.loads(t);assert not a['import_enabled']
  rows.append(dict(id=a['id'],bytes=len(t),sha256=digest(t)))
 assert m['coordinate_policy']['conversion_applied'] is False and m['validation']['unreal_editor_import_verified'] is False
 layout=json.loads((BASE/'scene/layout.json').read_text('utf8'));scene=read_glb((BASE/'scene/hall.glb').read_bytes())
 assert layout['cameras']==scene['extras']['sourceCameras']
 assert len(layout['player_markers'])==1 and len(layout['player_markers'][0]['matrix'])==16
 result=dict(passed=True,files=len(rows),scope='Byte-identical source asset handoff and GLB inventory; no Unreal execution',unreal_editor_verified=False,assets=rows)
 (BASE.parent/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8');return result
if __name__=='__main__':
 result=verify();print(json.dumps({k:v for k,v in result.items() if k!='assets'}))
