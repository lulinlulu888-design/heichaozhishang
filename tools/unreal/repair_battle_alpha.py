"""Versioned four-slot alpha repair; no engine launch and no implicit writes.

--plan in ordinary Python validates actual captured graph and pinned inputs.
In full Editor default mode is read-only verify. Only the explicit process flag
-HczsBattleAlphaApply creates four derived MIs and saves the current battle map.
The parent owns process serialization and source/native-frame acceptance.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/unreal/battle-alpha'
PROJECT=ROOT/'clients/unreal5 5.8'
MAP='/Game/Recovered/Battle/Maps/L_TutorialBattle'
BASE_MATERIAL='/InterchangeAssets/gltf/M_Unlit.M_Unlit'
BODY='/InterchangeAssets/gltf/MaterialBodies/MF_Unlit_Body.MF_Unlit_Body'
COLOR='/InterchangeAssets/gltf/MaterialFunctions/MF_BaseColor.MF_BaseColor'
sys.path.insert(0,str(ROOT/'tools/unreal'))
from audit_battle_alpha import ENGINE,sha,publish,graph_snapshot,scalar_parameters
from verify_battle_scene import input_plan,material_readback,content_hashes,obj_path

def canonical_graph(graph):
 """Exclude transient preview addresses; keep actual critical wiring/constants."""
 keys=('path','class_name','owner','inputs','input_names','input_output_names','parameter_name','default_value',
       'function','function_outputs','input_name','output_name','const_a','const_b')
 return dict(material=graph['material'],root=graph['opacity_mask_root'],output=graph['opacity_mask_output'],
  nodes=sorted([{k:n[k]for k in keys if k in n}for n in graph['nodes']],key=lambda n:n['path']))

def graph_semantics(graph):
 if graph.get('warnings') or graph['material']!=BASE_MATERIAL or graph['opacity_mask_output']!='OpacityMask':
  raise ValueError('Incomplete or different native opacity graph')
 nodes={n['path']:n for n in graph['nodes']}
 def node(owner,name,kind):
  value=nodes.get(owner+':'+name)
  if not value or value['class_name']!='MaterialExpression'+kind:raise ValueError('Reviewed alpha graph node changed: '+name)
  return value
 def inputs(value,expected):
  if value['inputs']!=expected:raise ValueError('Reviewed alpha graph wiring changed: '+value['path'])
 root=node(BASE_MATERIAL,'MaterialExpressionMaterialFunctionCall_1','MaterialFunctionCall')
 if graph['opacity_mask_root']!=root['path'] or root['function']!=BODY:raise ValueError('Opacity root does not call the reviewed unlit body')
 alpha=node(BASE_MATERIAL,'MaterialExpressionScalarParameter_0','ScalarParameter')
 if alpha.get('parameter_name')!='AlphaCutoff' or alpha.get('default_value')!=0:raise ValueError('Shared alpha parameter changed')
 i=root['input_names'].index('AlphaCutoff')
 if root['inputs'][i]!=alpha['path']:raise ValueError('Actual alpha scalar binding changed')
 output=node(BODY,'MaterialExpressionFunctionOutput_10','FunctionOutput')
 switch=node(BODY,'MaterialExpressionStaticSwitch_2','StaticSwitch')
 inputs(output,[switch['path']])
 if output['output_name']!='OpacityMask':raise ValueError('Wrong function output')
 choose=node(BODY,'MaterialExpressionStaticBoolParameter_2','StaticBoolParameter')
 if choose.get('parameter_name')!='bHasBaseColorTexture' or choose.get('default_value')is not True:raise ValueError('Source texture branch changed')
 reroute=node(BODY,'MaterialExpressionReroute_2','Reroute')
 call=node(BODY,'MaterialExpressionMaterialFunctionCall_6','MaterialFunctionCall')
 if switch['inputs'][0]!=reroute['path'] or switch['inputs'][2]!=choose['path']:raise ValueError('Source texture mask branch changed')
 inputs(reroute,[call['path']])
 if reroute['input_output_names']!=['OpacityMask'] or call['function']!=COLOR:raise ValueError('Texture mask output changed')
 body_alpha=node(BODY,'MaterialExpressionFunctionInput_105','FunctionInput')
 declaration=node(BODY,'MaterialExpressionNamedRerouteDeclaration_2','NamedRerouteDeclaration')
 inputs(declaration,[body_alpha['path']])
 if body_alpha['input_name']!='AlphaCutoff' or call['inputs'][call['input_names'].index('AlphaCutoff')]!=declaration['path']:
  raise ValueError('Unlit->BaseColor alpha scalar binding changed')
 mask=node(COLOR,'MaterialExpressionFunctionOutput_5','FunctionOutput')
 subtract=node(COLOR,'MaterialExpressionSubtract_1','Subtract')
 saturate=node(COLOR,'MaterialExpressionSaturate_1','Saturate')
 multiply=node(COLOR,'MaterialExpressionMultiply_5','Multiply')
 cutoff=node(COLOR,'MaterialExpressionFunctionInput_4','FunctionInput')
 factor=node(COLOR,'MaterialExpressionFunctionInput_5','FunctionInput')
 texture=node(COLOR,'MaterialExpressionTextureSample_0','TextureSample')
 inputs(mask,[subtract['path']]);inputs(subtract,[saturate['path'],cutoff['path']]);inputs(saturate,[multiply['path']]);inputs(multiply,[factor['path'],texture['path']])
 if mask['output_name']!='OpacityMask' or cutoff['input_name']!='AlphaCutoff' or factor['input_name']!='BaseColorFactor_A' or multiply['input_output_names']!=['','A']:
  raise ValueError('Actual raw alpha/channel/subtraction formula changed')
 return dict(verified=True,formula='OpacityMask = saturate(BaseColorFactor_A * Texture.A) - AlphaCutoff',
  repair_formula='discard if saturate(BaseColorFactor_A * Texture.A) - 0 - baseClip < 0',
  scalar_to_preserve=0.0,base_clip_to_restore=100.0/255.0,
  double_clip_prohibited='Setting both AlphaCutoff and baseClip to100/255 would discard until approximately200/255',
  scope='Reviewed actual UE graph + intended staged glTF MASK cutoff; original NeoX shading and visual equivalence remain unverified')

def repair_plan():
 staged=input_plan();raw=(BASE/'native-audit.json').read_bytes();audit=json.loads(raw)
 if audit.get('schema')!='hczs-battle-alpha-native-audit-v1' or audit.get('passed')is not True or audit.get('read_only')is not True:
  raise ValueError('Need a successful actual native graph/scalar audit')
 if audit['manifest_sha256']!=staged['manifest_sha256'] or audit['source_glb_sha256']!=staged['rows']['player']['record']['sha256']:
  raise ValueError('Native audit no longer matches the staged source')
 if len(audit['material_graphs'])!=1:raise ValueError('Unexpected shared parent graphs')
 graph=audit['material_graphs'][0];semantics=graph_semantics(graph)
 for filename,digest in audit['engine_source_fingerprints'].items():
  if sha((ENGINE/filename).read_bytes())!=digest:raise ValueError('Shared engine source/asset changed')
 mapping=[]
 for component,source in [(1,2),(2,1),(4,7),(8,4)]:
  row=next(r for r in audit['slots']if r['component_slot']==component)
  if row['source_slot']!=source or row['source_alpha_mode']!='MASK' or abs(row['source_alpha_cutoff']-100/255)>1e-9 or row['scalar_parameters'].get('AlphaCutoff')!=0:
   raise ValueError('Affected source slot/cutoff/actual scalar changed')
  if row['effective_properties']['opacity_mask_clip_value']!=0 or not row['path'].startswith('/Game/Recovered/Battle/Elsa/'):
   raise ValueError('The audited source slot is not the reviewed original MI')
  mapping.append(dict(component_slot=component,source_slot=source,original=row['path'],source_name=row['source_name'],cutoff=row['source_alpha_cutoff']))
 fingerprint=sha(json.dumps(canonical_graph(graph),sort_keys=True,separators=(',',':')).encode())
 identity=dict(schema='hczs-battle-alpha-repair-v1',manifest_sha256=staged['manifest_sha256'],source_glb_sha256=audit['source_glb_sha256'],
  engine_source_fingerprints=audit['engine_source_fingerprints'],graph_sha256=fingerprint,semantics=semantics,slots=mapping)
 recipe=sha(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())
 dest='/Game/Recovered/Battle/AlphaFix/v1_'+recipe[:16]
 for row in mapping:row['derived']=dest+'/'+row['original'].split('/')[-1].split('.')[0]
 return {**identity,'recipe_sha256':recipe,'native_audit_sha256':sha(raw),'destination':dest,
  'original_mesh_materials_preserved':True,'original_materials_textures_and_shared_parents_preserved':True,
  'map':MAP,'visual_verified':False,'original_neox_shader_verified':False}

def params(unreal,interface):
 edit=unreal.MaterialEditingLibrary
 vectors={}
 for name in edit.get_vector_parameter_names(interface):
  value=edit.get_material_instance_vector_parameter_value(interface,name);vectors[str(name)]=[float(value.r),float(value.g),float(value.b),float(value.a)]
 return dict(scalar=scalar_parameters(unreal,interface),vector=vectors,
  texture={str(name):obj_path(edit.get_material_instance_texture_parameter_value(interface,name))for name in edit.get_texture_parameter_names(interface)},
  static={str(name):bool(edit.get_material_instance_static_switch_parameter_value(interface,name))for name in edit.get_static_switch_parameter_names(interface)})

def context(unreal):
 if Path(unreal.Paths.get_project_file_path()).resolve()!=PROJECT/'Hczs.uproject' or not unreal.SystemLibrary.get_engine_version().startswith('5.8.'):
  raise RuntimeError('Use current project and UE5.8')
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.')[0]!=MAP:raise RuntimeError('Open only the existing saved tutorial battle map, outside PIE')
 actors=[a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()if a.actor_has_tag('HCZSBattlePlayer')]
 if len(actors)!=1:raise RuntimeError('Ambiguous source player actor')
 component=actors[0].get_component_by_class(unreal.SkeletalMeshComponent)
 if not component or component.get_num_materials()!=9:raise RuntimeError('Original nine-slot actor is unavailable')
 return world,component

def verify_in_memory(unreal,plan,component):
 results=[]
 for row in plan['slots']:
  interface=component.get_material(row['component_slot'])
  if obj_path(interface)!=row['derived']+'.'+row['derived'].split('/')[-1]:raise RuntimeError('Derived material binding is absent/wrong')
  if unreal.EditorAssetLibrary.get_metadata_tag(interface,'HczsBattleAlphaRecipeSHA256')!=plan['recipe_sha256']:raise RuntimeError('Derived material recipe changed')
  original=unreal.load_asset(row['original']);readback=material_readback(unreal,interface)
  actual=readback['effective_properties'];original_state=material_readback(unreal,original)['effective_properties']
  if abs(actual['opacity_mask_clip_value']-row['cutoff'])>1e-6 or any(actual[k]!=original_state[k]for k in ('blend_mode','two_sided','shading_model')):
   raise RuntimeError('Derived base-property readback differs')
  snapshot=params(unreal,interface)
  if snapshot!=params(unreal,original) or snapshot['scalar'].get('AlphaCutoff')!=0 or snapshot['static'].get('bHasBaseColorTexture')is not True:
   raise RuntimeError('Original texture/tint/UV/scalar/static parameters changed or source texture branch is inactive')
  if interface.get_editor_property('parent')!=original.get_editor_property('parent'):raise RuntimeError('Shared parent binding changed')
  results.append(dict(component_slot=row['component_slot'],source_slot=row['source_slot'],derived=obj_path(interface),effective_properties=actual,
   preserved_parameters=snapshot,effective_threshold=actual['opacity_mask_clip_value']+snapshot['scalar']['AlphaCutoff']))
 return results

def run_native(apply=False):
 import unreal
 plan=repair_plan();before=content_hashes();world,component=context(unreal)
 result={**plan,'schema':'hczs-battle-alpha-native-repair-v1'if apply else 'hczs-battle-alpha-native-verify-v1',
  'read_only':not apply,'passed':False,'map_saved':False,'results':[],'engine_version':unreal.SystemLibrary.get_engine_version()}
 before_overrides=list(component.get_editor_property('override_materials'))
 materials=[component.get_material(i)for i in range(9)]
 mesh=component.get_skinned_asset();mesh_slots=[obj_path(s.get_editor_property('material_interface'))for s in mesh.get_editor_property('materials')]
 try:
  graph=graph_snapshot(unreal,unreal.load_asset(BASE_MATERIAL));graph_semantics(graph)
  if sha(json.dumps(canonical_graph(graph),sort_keys=True,separators=(',',':')).encode())!=plan['graph_sha256']:
   raise RuntimeError('Live native opacity graph differs from reviewed evidence')
  if apply:
   if unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():raise RuntimeError('Unsaved map changes exist; save/review them before this bounded repair')
   if unreal.EditorAssetLibrary.list_assets(plan['destination'],True,False):raise RuntimeError('Version namespace already exists; verify it rather than overwriting')
   originals={}
   for row in plan['slots']:
    original=materials[row['component_slot']]
    if obj_path(original)!=row['original']or not isinstance(original,unreal.MaterialInstanceConstant):raise RuntimeError('Original source-slot interface changed')
    p=params(unreal,original)
    if p['scalar'].get('AlphaCutoff')!=0 or p['static'].get('bHasBaseColorTexture')is not True or not p['texture'].get('BaseColorTexture'):
     raise RuntimeError('Actual texture branch/scalar gate is not satisfied')
    if material_readback(unreal,original)['effective_properties']['opacity_mask_clip_value']!=0:raise RuntimeError('Original cutoff changed since audit')
    originals[row['component_slot']]=p
   # Backup only after all read-only preflight gates and before any asset changes.
   map_file=PROJECT/'Content/Recovered/Battle/Maps/L_TutorialBattle.umap'
   backup=BASE/'backups'/('v1_'+plan['recipe_sha256'][:16]);backup.mkdir(parents=True,exist_ok=False)
   raw_map=map_file.read_bytes();(backup/'L_TutorialBattle.umap').write_bytes(raw_map)
   backup_record=dict(recipe_sha256=plan['recipe_sha256'],map=MAP,map_sha256=sha(raw_map),
    original_effective_materials=[obj_path(m)for m in materials],before_override_materials=[obj_path(m)for m in before_overrides],
    original_mesh=obj_path(mesh),original_mesh_materials=mesh_slots,original_battle_content=before,plan=plan)
   (backup/'backup.json').write_text(json.dumps(backup_record,ensure_ascii=False,indent=2),'utf8')
   result['backup']=backup.relative_to(ROOT).as_posix();result['backup_map_sha256']=sha(raw_map)
   derived={}
   for row in plan['slots']:
    package=unreal.EditorAssetLibrary.duplicate_asset(row['original'],row['derived'])
    if not isinstance(package,unreal.MaterialInstanceConstant):raise RuntimeError('Could not duplicate this original project MI')
    overrides=package.get_editor_property('base_property_overrides')
    overrides.set_editor_property('bOverride_OpacityMaskClipValue',True)
    overrides.set_editor_property('OpacityMaskClipValue',row['cutoff'])
    package.set_editor_property('base_property_overrides',overrides)
    unreal.MaterialEditingLibrary.update_material_instance(package)
    if params(unreal,package)!=originals[row['component_slot']]:raise RuntimeError('Duplicate lost original material parameters')
    unreal.EditorAssetLibrary.set_metadata_tag(package,'HczsBattleAlphaRecipeSHA256',plan['recipe_sha256'])
    unreal.EditorAssetLibrary.set_metadata_tag(package,'HczsBattleAlphaOriginalInterface',row['original'])
    unreal.EditorAssetLibrary.set_metadata_tag(package,'HczsBattleAlphaSourceSlot',str(row['source_slot']))
    unreal.EditorAssetLibrary.set_metadata_tag(package,'HczsBattleAlphaScope','Staged glTF MASK threshold; not original NeoX shader equality')
    if not unreal.EditorAssetLibrary.save_loaded_asset(package,only_if_is_dirty=False):raise RuntimeError('Cannot save the versioned derived MI')
    derived[row['component_slot']]=package
   for slot,package in derived.items():component.set_material(slot,package)
   result['results']=verify_in_memory(unreal,plan,component)
   if [obj_path(s.get_editor_property('material_interface'))for s in mesh.get_editor_property('materials')]!=mesh_slots:raise RuntimeError('Original mesh material slots changed')
   if not unreal.EditorLoadingAndSavingUtils.save_map(world,MAP):raise RuntimeError('Cannot save the bounded actor-only map assignment')
   result['map_saved']=True
  else:result['results']=verify_in_memory(unreal,plan,component)
  after=content_hashes()
  allowed_prefix='AlphaFix/v1_'+plan['recipe_sha256'][:16]+'/'
  protected={k:v for k,v in before.items()if k!='Maps/L_TutorialBattle.umap'and not k.startswith(allowed_prefix)}
  if any(after.get(k)!=v for k,v in protected.items()):raise RuntimeError('Existing protected Battle assets changed')
  if not apply and before!=after:raise RuntimeError('Read-only native verification changed saved content')
  if any(sha((ENGINE/p).read_bytes())!=h for p,h in plan['engine_source_fingerprints'].items()):raise RuntimeError('Shared engine assets or importer source changed')
  result.update(original_battle_assets_preserved=True,original_mesh_materials_preserved=True,
   source_glb_preserved=input_plan()['rows']['player']['record']['sha256']==plan['source_glb_sha256'],
   graph_semantics_verified=True,visual_verified=False,original_neox_shader_verified=False,passed=True)
 except Exception:
  result['error']=traceback.format_exc()
  if apply and not result['map_saved']:component.set_editor_property('override_materials',before_overrides)
 finally:
  result['battle_content_after']=content_hashes()
  publish('repair-result.json'if apply else 'repair-native-verify.json',result)
 if not result['passed']:raise RuntimeError(result.get('error','Alpha repair/verification failed'))
 unreal.log('HCZS alpha '+('repair saved; fresh-process readback and frame still required'if apply else 'read-only derived graph/threshold verification passed'))
 return result

if __name__=='__main__':
 if '--plan'in sys.argv:
  plan=repair_plan();publish('repair-plan.json',plan);print(json.dumps(plan,ensure_ascii=False,indent=2))
 else:
  import unreal
  command=' '+unreal.SystemLibrary.get_command_line()+' '
  run_native(apply=' -HczsBattleAlphaApply 'in command)
