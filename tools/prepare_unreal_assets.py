"""Stage recovered originals for UE5; never synthesize .uasset/.umap or change GLB units."""
import argparse,json,struct
from pathlib import Path
from verify_unreal_assets import ROOT,BASE,digest,read_glb,glb_summary,verify

def main():
 BASE.mkdir(parents=True,exist_ok=True);assets=[]
 def load(p):return json.loads((ROOT/p).read_text('utf8'))
 def stage(identifier,source,target,kind,category,dest,expected=None):
  source=Path(source);source=source if source.is_absolute() else ROOT/source
  if not source.resolve().is_relative_to(ROOT):raise ValueError('Source outside project')
  data=source.read_bytes();sha=digest(data)
  if expected and sha!=expected:raise ValueError('Source report digest mismatch: '+identifier)
  output=BASE/target;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
  row=dict(id=identifier,kind=kind,category=category,file=target,source_file=source.relative_to(ROOT).as_posix(),source_sha256=sha,sha256=sha,bytes=len(data),import_path=dest,import_enabled=kind!='metadata')
  if kind.startswith('gltf_'):row['geometry']=glb_summary(read_glb(data))
  if kind=='texture':row['dimensions']=list(struct.unpack_from('>II',data,16))
  assets.append(row);return data
 scene_report=load('analysis/hall/midgard_home_3d/export.json')
 scene=read_glb(stage('hall_scene','analysis/hall/midgard_home_3d/scene.glb','scene/hall.glb','gltf_scene','environment','/Game/Recovered/Hall/Environment',scene_report['sha256']))
 stage('hall_export_evidence','analysis/hall/midgard_home_3d/export.json','evidence/hall-export.json','metadata','evidence','/Game/Recovered/Hall/Evidence')
 for name,folder,filename in [('shiranui','export','shiranui-idle.colour-reference.glb'),('shiranui_weapon','export-weapon','shiranuiweapon-idle.colour-reference.glb')]:
  base='analysis/characters/shiranui/'+folder;report=load(base+'/export-report.json')
  stage(name,base+'/'+filename,'characters/'+name+'.glb','gltf_skeletal_mesh','character','/Game/Recovered/Shiranui/'+name,report['sha256'])
  stage(name+'_export_evidence',base+'/export-report.json','evidence/'+name+'-export.json','metadata','evidence','/Game/Recovered/Shiranui/Evidence')
 lightbase='analysis/hall/lighting/';lighting=load(lightbase+'lighting.json')
 if lighting['scene_glb_sha256']!=scene_report['sha256']:raise ValueError('Lightmaps refer to another scene')
 stage('hall_lighting',lightbase+'lighting.json','lighting/lighting.json','metadata','lighting','/Game/Recovered/Hall/Lighting')
 for i,t in enumerate(lighting['textures']):stage('hall_lightmap_'+str(i),lightbase+t['file'],'lighting/'+t['file'],'texture','lightmap','/Game/Recovered/Hall/Lighting',t['sha256'])
 fxbase='analysis/characters/shiranui/effects/render-inputs/';fx=load(fxbase+'manifest.json')
 stage('flame_geometry',fxbase+'flame-01.glb','flame/flame-01.glb','gltf_static_mesh','effect','/Game/Recovered/Shiranui/Flame',fx['geometry_sha256'])
 stage('flame_parameters',fxbase+'manifest.json','flame/material-and-sfx.json','metadata','effect','/Game/Recovered/Shiranui/Flame')
 stage('flame_attachment',fxbase+'attachment.json','flame/attachment.json','metadata','effect','/Game/Recovered/Shiranui/Flame')
 for i,t in enumerate(fx['textures']):
  image=t['outputs'][0];stage('flame_texture_'+str(i),image['png'],'flame/texture-'+str(i)+'.png','texture','effect_texture','/Game/Recovered/Shiranui/Flame',image['png_sha256'])
 layout=dict(cameras=scene['extras']['sourceCameras'],player_markers=[dict(name=n.get('name'),matrix=n['matrix'],source=n['extras']['sourceInstance']) for n in scene['nodes'] if n.get('extras',{}).get('sourceInstance',{}).get('Name')=='player_position'],source_scene_sha256=scene_report['sha256'],matrix_convention='Original column-major source matrices, not converted to Unreal',reference_character_scale=.86,reference_scale_scope='Existing hall reconstruction uses source SCALE_IN_HALL; no UE actor scaling applied')
 layout_source=ROOT/'analysis/unreal/source-layout.json';layout_source.parent.mkdir(parents=True,exist_ok=True);layout_source.write_text(json.dumps(layout,ensure_ascii=False,indent=2),'utf8')
 stage('scene_layout',layout_source,'scene/layout.json','metadata','layout','/Game/Recovered/Hall/Layout')
 manifest=dict(schema='hczs-unreal-import-inputs-v1',assets=assets,coordinate_policy=dict(source='glTF Y-up right-handed container preserving original recovered XYZ values',target='UE Z-up left-handed world; physical source-unit-to-centimeter factor is unverified',conversion_applied=False,importer_action='Use explicit editor importer conversion once; verify orientation, winding, skeleton, animation, sockets and camera before choosing units',forbidden='Do not rescale or overwrite source GLBs to hide rendering artifacts'),validation=dict(unreal_editor_import_verified=False,unreal_materials_verified=False,native_platforms_verified=False),metadata=dict(layout='scene/layout.json',lighting='lighting/lighting.json',effects='flame/material-and-sfx.json',attachments='flame/attachment.json'),limitations=['This is an import-input handoff, not .uasset/.umap output','GLB materials are colour-reference unlit adapters; original lighting/SFX parameters need UE reconstruction','Raw matrices are not Unreal actor transforms; camera forward and source socket conventions require editor checks','Animation counts and bytes are preserved; importer resampling/coordinate conversion remains unverified'])
 (BASE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8')
 print(json.dumps(dict(files=len(assets),verification=verify()['passed'],manifest=str(BASE/'manifest.json'))))
 add_elsa()

def add_elsa():
 """Append verified initial-character handoff while retaining existing entries.

 Use the actual home_stand_idle_1 clip recovered from the source configuration,
 never substitute or rename the old stand_idle + skin inspection GLB.
 """
 from trace_first_encounter import literal_table
 from verify_unreal_assets import contained
 manifest_path=BASE/'manifest.json'
 manifest=json.loads(manifest_path.read_text('utf8'))
 if manifest['schema']!='hczs-unreal-import-inputs-v1':raise ValueError('Unsupported handoff schema')
 old=[a for a in manifest['assets'] if a['id'] not in ('elsa','elsa_export_evidence','elsa_selection_evidence')]
 if len({a['id'] for a in old})!=len(old):raise ValueError('Duplicate existing handoff IDs')
 source=ROOT/'analysis/elsa-hall/elsa-hall-idle.colour-reference.glb'
 report=json.loads((ROOT/'analysis/elsa-hall/export-report.json').read_text('utf8'))
 model_report=json.loads((ROOT/'analysis/elsa-model/export-report.json').read_text('utf8'))
 data=source.read_bytes();doc=read_glb(data)
 if digest(data)!=report['sha256'] or digest(data)!='823397c87ae22bbdaa1fc20b07352da0b2b3a252d0f755fb1998dd5d2578b193':raise ValueError('Elsa original hall animation GLB changed')
 if report['base_glb_sha256']!=model_report['glb_sha256']:raise ValueError('Elsa source model relationship changed')
 for item in model_report['sources'].values():
  original=Path(item['sample_path']).resolve()
  if not original.is_relative_to(ROOT.resolve()) or digest(original.read_bytes())!=item['sha256']:raise ValueError('Elsa decoded source changed')
 character=literal_table(8995,{1});entities=literal_table(1955,{0,20});lod=literal_table(1268,{201});levels=literal_table(6328,{16,17,18,19})
 char=character['rows'][0]['fields'];entity_rows={r['id']:r['fields'] for r in entities['rows']}
 level=next(r['fields'] for r in levels['rows'] if r['id']==16)
 if char['NAME']!='艾尔莎' or char['InitChar'] is not True or char['ENTITY_ID']!=0 or char['CULTIVATE_ENTITY_ID']!=20:raise ValueError('Initial-character source mapping changed')
 if any(e['LOD_ID']!=201 or e['ANIM_STATES_HOME_STAND_IDLE']!='home_stand_idle_1' for e in entity_rows.values()):raise ValueError('Elsa hall configuration changed')
 if lod['rows'][0]['fields']['LOD_MODEL_LIST']!=[16,17,18,19] or level['LEVEL']!=0 or level['MODEL_PATH']!='character/player/ailisha/ailisha_yangcheng.gim':raise ValueError('Elsa highest-detail source selection changed')
 clip_names=[a['name'] for a in doc['animations']]
 if clip_names!=['home_stand_idle_1']:raise ValueError('Elsa hall animation inventory changed')
 selection=dict(character_id=1,name='艾尔莎',initial_character_source_verified=True,
  selected_model=level['MODEL_PATH'],source_lod_row=16,source_lod_level=0,
  source_model_provenance=model_report['sources'],source_reference_scale=entity_rows[0]['SCALE_IN_HALL'],
  available_clip_names=clip_names,source_hall_clip='home_stand_idle_1',hall_animation_available=True,
  source_hall_clip_path='character/player/ailisha/ailisha_gis_acl/home_stand_idle_1.gisacl',
  shader_scope='Original mesh/UV/images with unlit colour-reference adapter; original NeoX toon/materials not restored',
  known_bind_difference=report['known_bind_difference'],
  evidence_kind='Ordinary static decoded-table/source-file evidence; no new REA Evidence or original-client execution',
  tables=dict(character=character,entities=entities,lod=lod,levels=levels))
 selection_path=ROOT/'analysis/unreal/elsa-source-selection.json'
 selection_path.write_text(json.dumps(selection,ensure_ascii=False,indent=2),'utf8')
 added=[]
 def stage(identifier,path,target,kind):
  payload=path.read_bytes();output=contained(BASE,target);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(payload)
  row=dict(id=identifier,kind=kind,category='character' if kind.startswith('gltf_') else 'evidence',
   file=target,source_file=path.relative_to(ROOT).as_posix(),source_sha256=digest(payload),sha256=digest(payload),
   bytes=len(payload),import_path='/Game/Recovered/Elsa' if identifier=='elsa' else '/Game/Recovered/Elsa/Evidence',import_enabled=kind!='metadata')
  if kind.startswith('gltf_'):row.update(geometry=glb_summary(read_glb(payload)),character_id=1,
   source_lod=dict(row=16,level=0,model_path=level['MODEL_PATH']),
   animation_scope=dict(available_clips=clip_names,required_hall_clip='home_stand_idle_1',hall_animation_available=True))
  added.append(row)
 stage('elsa',source,'characters/elsa.glb','gltf_skeletal_mesh')
 stage('elsa_export_evidence',ROOT/'analysis/elsa-hall/export-report.json','evidence/elsa-export.json','metadata')
 stage('elsa_selection_evidence',selection_path,'evidence/elsa-selection.json','metadata')
 manifest['assets']=old+added
 manifest.setdefault('metadata',{})['initial_character_selection']='evidence/elsa-selection.json'
 pending=manifest_path.with_suffix('.json.pending');pending.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8');pending.replace(manifest_path)
 result=verify()
 print(json.dumps(dict(files=result['files'],added=[a['id'] for a in added],verification=result['passed'],
  source_lod_level=0,available_clips=clip_names,hall_animation_available=True)))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--add-elsa-only',action='store_true',help='Preserve existing handoff entries and append the initial character without rebuilding prior selections')
 args=parser.parse_args()
 if args.add_elsa_only:add_elsa()
 else:main()
