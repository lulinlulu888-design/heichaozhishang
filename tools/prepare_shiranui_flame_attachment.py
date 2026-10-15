"""Compile source socket/SFX hierarchy for the bounded flame reference player."""
import hashlib,json,math
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 base=ROOT/'analysis/characters/shiranui'
 audit=json.loads((base/'asset-audit.json').read_text('utf8'))
 manifest=json.loads((base/'effects/render-inputs/manifest.json').read_text('utf8'))
 source=audit['sources']['character/player/buzhihuo/buzhihuo_weapon.gim']
 raw=Path(source['sample_path']).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('GIM changed')
 sockets=[]
 for node in ET.fromstring(raw).find('Sockets'):
  for obj in node.findall('BoundObject/Object'):
   if obj.get('Active')!='true':continue
   path=obj.get('Name').replace('\\','/')
   if not path.endswith(('ui_idle_3.sfx','ui_idle_4.sfx')):raise ValueError('Unsupported attachment')
   matrix=list(map(float,node.get('MatrixToBone').split(',')))
   if len(matrix)!=16 or not all(map(math.isfinite,matrix)):raise ValueError('Invalid matrix')
   sockets.append(dict(name=node.get('Name'),bone=node.get('BoneName'),matrix=matrix,effect=path,source_attributes=node.attrib))
 effects={};counts={'models':0,'ignored_subtrees':0}
 def constant(node):
  frames=[c for c in node['children'] if c['tag']=='Frame']
  if len(frames)!=1:raise ValueError('Animated curve requires explicit interpolation')
  values=list(map(float,frames[0]['attributes']['Value'].split(',')))
  if not all(map(math.isfinite,values)):raise ValueError('Nonfinite curve')
  return values[0] if len(values)==1 else values
 def compile_node(node):
  a=node['attributes'];tag=node['tag']
  if a.get('FxIgnore')=='TRUE':counts['ignored_subtrees']+=1;return None
  if tag not in ('FxGroup','Dummy','Model'):raise ValueError('Unsupported active effect '+tag)
  out=dict(tag=tag,attributes=a,position=list(map(float,a.get('PosOffset','0,0,0').split(','))),scale=[1,1,1],children=[])
  for c in node['children']:
   t=c['tag']
   if t in ('Dummy','Model','ParticleRes','Sprite'):
    value=compile_node(c)
    if value:out['children'].append(value)
   elif t=='TrackScale':
    out['scale']=[constant(next(v for v in c['children'] if v['tag']==axis+'Scale')) for axis in 'XYZ']
   elif t=='TrackFixPoint':out['forward']=list(map(float,c['attributes']['Forward'].split(',')))
   elif t=='ScaleFrame':out['model_scale']=constant(c)
   elif t=='ShaderComponent':
    u=next(v for v in c['children'] if v['tag']=='Uniforms')
    out['uniforms']={v['tag'].removesuffix('_Keyframe'):constant(v) for v in u['children'] if v['tag']!='Variables'}
   else:raise ValueError('Unsupported active child '+t)
  if tag=='Model':
   if not a['ModelName'].replace('\\','/').endswith('/ui_idle_huoyan_01_uv.gim'):raise ValueError('Unexpected active geometry')
   counts['models']+=1
  return out
 for f in manifest['source_effects']:
  path=f['source']['logical_path']
  if path not in {s['effect'] for s in sockets}:continue
  data=Path(f['source']['sample_path']).read_bytes()
  if hashlib.sha256(data).hexdigest()!=f['source']['sha256']:raise ValueError('SFX changed')
  def tree(e):return dict(tag=e.tag,attributes=e.attrib,children=[tree(c) for c in e])
  effects[path]=compile_node(tree(ET.fromstring(data.decode('gb18030'))))
 report=dict(source=source,sockets=sockets,effects=effects,counts=counts,
  evidence_kind='Ordinary hash-checked extracted XML; not original engine execution or new REA Evidence',
  assumptions=['MatrixToBone interpreted as column-major local socket matrix under named animated bone',
   'TrackFixPoint Forward interpreted as xyz rotation axis plus angle in degrees; native interpretation unverified',
   'Single ScaleFrame value multiplied with TrackScale; ChangeType4 native timing unverified',
   'Constant layers kept alive for preview; original lifecycle and quality filtering unverified',
   'TransparentMode2 uses alpha blend, mode0 additive reference adaptation; native enum unverified'])
 target=base/'effects/render-inputs/attachment.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
 print(json.dumps(dict(sockets=len(sockets),**counts)))
if __name__=='__main__':main()
