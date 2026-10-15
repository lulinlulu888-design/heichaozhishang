"""Read-only native alpha graph/scalar evidence; root owns UE execution.

Open the saved L_TutorialBattle in the full 5.8.3 Editor and execute this file.
No material/map save, recompile, parameter mutation or engine launch occurs.
Ordinary Python --plan only validates staged sources and existing readback.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/unreal/battle-alpha'
sys.path.insert(0,str(ROOT/'tools/unreal'))
from verify_battle_scene import input_plan,material_readback,content_hashes,source_material_name,obj_path
ENGINE=Path('D:/Program Files/Epic Games/UE_5.8/Engine')
SOURCE_FILES=[
 'Plugins/Interchange/Runtime/Source/Import/Private/Gltf/InterchangeGLTFMaterial.cpp',
 'Plugins/Interchange/Runtime/Source/Import/Public/Gltf/InterchangeGLTFMaterial.h',
 'Plugins/Interchange/Assets/Content/gltf/M_Unlit.uasset',
 'Plugins/Interchange/Assets/Content/gltf/MaterialBodies/MF_Unlit_Body.uasset',
 'Plugins/Interchange/Assets/Content/gltf/MaterialFunctions/MF_BaseColor.uasset']

def sha(data):return hashlib.sha256(data).hexdigest()
def publish(filename,value):
 BASE.mkdir(parents=True,exist_ok=True)
 path=BASE/filename
 if path.exists():
  old=path.read_bytes();archived=BASE/'attempts'/('report-'+sha(old)+'.json');archived.parent.mkdir(exist_ok=True)
  if archived.exists() and archived.read_bytes()!=old:raise RuntimeError('Audit archive digest conflict')
  if not archived.exists():archived.write_bytes(old)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),'utf8')

def source_plan():
 plan=input_plan();previous=ROOT/'analysis/unreal/battle-inputs/native-readback.json'
 raw=previous.read_bytes();readback=json.loads(raw)
 if readback.get('schema')!='hczs-battle-native-readback-v1' or readback.get('manifest_sha256')!=plan['manifest_sha256']:
  raise ValueError('Native readback does not match the validated battle handoff')
 rows=[]
 for row in readback['combatants']['player']['materials']:
  source=row['staged_source_material']
  actual=row['effective_properties']['opacity_mask_clip_value']
  if source.get('alphaMode')=='MASK' and abs(actual-source.get('alphaCutoff',.5))>1e-5:
   rows.append(dict(component_slot=row['slot'],source_slot=source['extras']['sourceMaterial']['slot'],source_name=source['name'],
    original_interface=row['path'],expected_cutoff=source.get('alphaCutoff',.5),actual_cutoff=actual,
    source_render_states=source['extras']['sourceMaterial']['render_states']))
 if [(r['component_slot'],r['source_slot'])for r in rows]!=[(1,2),(2,1),(4,7),(8,4)]:
  raise ValueError('The reviewed four affected source/component slots changed')
 fingerprints={p:sha((ENGINE/p).read_bytes())for p in SOURCE_FILES}
 return dict(schema='hczs-battle-alpha-source-plan-v1',manifest_sha256=plan['manifest_sha256'],
  native_readback_sha256=sha(raw),affected=rows,engine_source_fingerprints=fingerprints,
  source_glb_sha256=plan['rows']['player']['record']['sha256'],original_neox_shader_verified=False,
  scope='Preserve staged glTF colour-reference MASK semantics; not original NeoX shading equivalence')

def scalar_parameters(unreal,interface):
 library=unreal.MaterialEditingLibrary
 names=[str(n)for n in library.get_scalar_parameter_names(interface)]
 return {name:float(library.get_material_instance_scalar_parameter_value(interface,name))
  if isinstance(interface,unreal.MaterialInstanceConstant) else float(library.get_material_default_scalar_parameter_value(interface,name)) for name in names}

def safe_value(obj,name):
 try:
  value=obj.get_editor_property(name)
  if value is None or isinstance(value,(str,int,float,bool)):return value
  if hasattr(value,'get_path_name'):return value.get_path_name()
  for fields in (('r','g','b','a'),('x','y','z','w')):
   if all(hasattr(value,c)for c in fields):return [float(getattr(value,c))for c in fields]
  return str(value)
 except Exception:return None

def graph_snapshot(unreal,material):
 """Record actual linked inputs/functions, retaining unsupported nodes as unknown.

 This is graph evidence, not an automatic interpretation of shader arithmetic.
 AlphaCutoff presence alone cannot authorize a threshold repair.
 """
 library=unreal.MaterialEditingLibrary;records={};functions={};warnings=[]
 root=library.get_material_property_input_node(material,unreal.MaterialProperty.MP_OPACITY_MASK)
 output=library.get_material_property_input_node_output_name(material,unreal.MaterialProperty.MP_OPACITY_MASK)
 def walk(owner,node):
  if node is None:return None
  path=obj_path(node)
  if path in records:return path
  if len(records)>=512:raise RuntimeError('Alpha graph exceeds bounded inspection')
  row=dict(path=path,class_name=node.get_class().get_name(),owner=obj_path(owner),inputs=[])
  records[path]=row
  for name in ('parameter_name','default_value','input_name','output_name','preview_value','use_preview_value_as_default','input_type',
               'const_a','const_b','const_greater_than','const_less_than','const_equals','equals_threshold',
               'min_default','max_default','r','g','b','a','value'):
   value=safe_value(node,name)
   if value is not None:row[name]=value
  try:row['input_names']=[str(n)for n in library.get_material_expression_input_names(node)]
  except Exception as e:warnings.append(dict(node=path,unavailable='input_names',reason=str(e)))
  try:
   inputs=library.get_inputs_for_material_expression(owner,node) if isinstance(owner,unreal.Material) else library.get_inputs_for_material_function_expression(owner,node)
   row['inputs']=[walk(owner,value)for value in inputs]
   links=[]
   for value in inputs:
    name=None
    if value is not None:
     try:
      connection=library.get_input_node_output_name_for_material_expression(node,value)
      if isinstance(connection,tuple):name=connection[-1] if connection[0] else None
      elif isinstance(connection,str):name=connection
     except Exception as e:warnings.append(dict(node=path,unavailable='input_output_name',reason=str(e)))
    links.append(name)
   row['input_output_names']=links
  except Exception as e:warnings.append(dict(node=path,unavailable='linked_inputs',reason=str(e)))
  if isinstance(node,unreal.MaterialExpressionMaterialFunctionCall):
   function=node.get_editor_property('material_function');row['function']=obj_path(function)
   outputs=[]
   try:
    # FunctionOutputs is not Python-visible in 5.8 despite a native UPROPERTY.
    # The engine's explicit read-only editing-library enumerator is exposed.
    for expression in library.get_material_function_expressions(function):
     if isinstance(expression,unreal.MaterialExpressionFunctionOutput):
      outputs.append(dict(name=safe_value(expression,'output_name'),expression=walk(function,expression)))
    row['function_outputs']=outputs
   except Exception as e:warnings.append(dict(node=path,unavailable='function_outputs',reason=str(e)))
   if function: functions[obj_path(function)]=dict(path=obj_path(function),outputs=outputs)
  return path
 root_path=walk(material,root)
 return dict(material=obj_path(material),opacity_mask_root=root_path,opacity_mask_output=str(output),nodes=list(records.values()),
  functions=list(functions.values()),warnings=warnings,
  automatic_semantic_approval=False,interpretation='Inspect the actual OpacityMask path and resolved AlphaCutoff inputs before choosing property/scalar correction; unknown graph shapes fail the repair gate.')

def audit_native():
 import unreal
 plan=source_plan();before=content_hashes()
 result={**plan,'schema':'hczs-battle-alpha-native-audit-v1','read_only':True,'passed':False,'slots':[],
  'material_graphs':[],'graph_semantics_verified':False,'assets_modified':False}
 try:
  if Path(unreal.Paths.get_project_file_path()).resolve()!=ROOT/'clients/unreal5 5.8/Hczs.uproject' or not unreal.SystemLibrary.get_engine_version().startswith('5.8.'):
   raise RuntimeError('Use the current Hczs UE5.8 project')
  editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);world=editor.get_editor_world()
  if world.get_path_name().split('.')[0]!='/Game/Recovered/Battle/Maps/L_TutorialBattle':raise RuntimeError('Open the existing tutorial battle map first')
  actors=[a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if a.actor_has_tag('HCZSBattlePlayer')]
  if len(actors)!=1:raise RuntimeError('Expected exactly one tagged original player')
  component=actors[0].get_component_by_class(unreal.SkeletalMeshComponent)
  if not component or component.get_num_materials()!=9:raise RuntimeError('Expected actual source nine-slot player')
  documents=input_plan()['rows']['player']['document'];shared={}
  for index in range(9):
   interface=component.get_material(index)
   candidates=[m for m in documents['materials'] if interface and source_material_name(m['name'])==interface.get_name()]
   if len(candidates)!=1:raise RuntimeError('Ambiguous actual source-slot mapping')
   row=material_readback(unreal,interface);row.update(component_slot=index,source_slot=candidates[0]['extras']['sourceMaterial']['slot'],
    source_name=candidates[0]['name'],source_alpha_mode=candidates[0].get('alphaMode','OPAQUE'),source_alpha_cutoff=candidates[0].get('alphaCutoff',.5),
    scalar_parameters=scalar_parameters(unreal,interface))
   root=interface
   while isinstance(root,unreal.MaterialInstance):root=root.get_editor_property('parent')
   if not isinstance(root,unreal.Material):raise RuntimeError('Unsupported base material')
   shared[obj_path(root)]=root;row['base_material']=obj_path(root);result['slots'].append(row)
  result['material_graphs']=[graph_snapshot(unreal,m)for m in shared.values()]
  result.update(engine_version=unreal.SystemLibrary.get_engine_version(),project=unreal.Paths.get_project_file_path(),map=world.get_path_name(),
   engine_source_files_unchanged=all(sha((ENGINE/p).read_bytes())==h for p,h in plan['engine_source_fingerprints'].items()))
  result['passed']=True
 except Exception:result['error']=traceback.format_exc()
 finally:
  result['saved_battle_content_unchanged']=content_hashes()==before
  result['passed']=result['passed'] and result['saved_battle_content_unchanged'] and result.get('engine_source_files_unchanged',False)
  publish('native-audit.json',result)
 if not result['passed']:raise RuntimeError(result.get('error','Read-only alpha audit changed content'))
 unreal.log('HCZS alpha graph/scalar audit captured; semantics still require review: '+str(BASE/'native-audit.json'))
 return result

if __name__=='__main__':
 if '--plan' in sys.argv:
  result=source_plan();publish('source-plan.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
 else:audit_native()
