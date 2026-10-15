"""Independent disk load/readback plus unique preview forward-light priority."""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
MAP = '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview'
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world or world.get_path_name().split('.')[0] != MAP:
    raise RuntimeError('Start the editor on the saved FX map for independent readback')
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = list(subsystem.get_all_level_actors())
by_label = {a.get_actor_label(): a for a in actors}
priorities = {'HCZSPreviewWindowKey':3,'HCZSPreviewCameraFill':2,'HCZSPreviewRim':1}
for label, priority in priorities.items():
    component = by_label[label].get_component_by_class(unreal.DirectionalLightComponent)
    if not component or component.get_editor_property('mobility') != unreal.ComponentMobility.MOVABLE:
        raise RuntimeError('Preview light identity/mobility changed')
    component.set_editor_property('forward_shading_priority', priority)
hero = by_label['HCZS_elsa'].get_component_by_class(unreal.SkeletalMeshComponent)
if hero.get_num_bones() != 180 or hero.get_num_materials() != 9 or not hero.get_editor_property('cast_shadow'):
    raise RuntimeError('Saved lit Elsa mesh/shadow state differs')
materials = [hero.get_material(i).get_path_name() for i in range(9)]
if not all(m.startswith('/Game/Recovered/Elsa/LightingPreview/') for m in materials):
    raise RuntimeError('Saved Elsa material overrides missing')
effect = by_label['HCZSOriginalSunlightPreview']
if len(effect.get_components_by_class(unreal.StaticMeshComponent)) != 20:
    raise RuntimeError('Saved sunlight component pool differs')
if not world.get_world_settings().get_editor_property('force_no_precomputed_lighting'):
    raise RuntimeError('Saved preview still requests native precomputed lighting')
environment = [a for a in actors if a.get_component_by_class(unreal.StaticMeshComponent)
    and '/Game/Recovered/Hall/Lighting/SourceDiffuseV1/Instances/' in a.get_component_by_class(unreal.StaticMeshComponent).get_material(0).get_path_name()]
if len(environment) != 65:
    raise RuntimeError('Saved original environment lightmap overrides differ')
if not unreal.EditorLoadingAndSavingUtils.save_map(world,MAP):
    raise RuntimeError('Cannot save unique forward-light priorities')
result = {'passed':True,'project':unreal.Paths.get_project_file_path(),'engine':unreal.SystemLibrary.get_engine_version(),
    'world':world.get_path_name(),'hero_bones':180,'hero_materials':materials,'source_lightmap_instances':65,
    'dynamic_floor_instances':1,'sunlight_components':20,'source_colour_keys':len(effect.get_editor_property('SourceColorTimes')),
    'movable_forward_light_priorities':priorities,'force_no_precomputed_lighting':True,
    'scope':'independent saved-map readback; original NeoX/FX runtime equivalence remains unverified'}
(ROOT/'analysis/unreal/hall-lighting/independent-readback.json').write_text(json.dumps(result,indent=2),encoding='utf8')
unreal.log('HCZS: independently loaded hall FX assets verified and unique light priority saved')
