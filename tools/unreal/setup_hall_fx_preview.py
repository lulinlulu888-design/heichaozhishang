"""Save an independent hall with source irradiance, lit Elsa and sunlight dust.

Real UE lights/shadows use explicit temporary inspection parameters. Native
NeoX shading/emission parity is not claimed. Start the full editor on SOURCE.
"""
import hashlib
import json
import sys
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
SOURCE = '/Game/Recovered/Hall/Maps/L_ElsaHallLightingPreview'
TARGET = '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview'
DEST = '/Game/Recovered/Hall/Lighting/DynamicPreviewV1'
REPORT = ROOT / 'analysis/unreal/hall-lighting/fx-preview-result.json'


def main():
    from apply_hall_lighting import package_file
    from apply_elsa_lighting_materials import apply_elsa_lighting_materials
    from apply_hall_sunlight import apply_hall_sunlight
    if unreal.EditorAssetLibrary.does_asset_exist(TARGET):
        raise RuntimeError('Independent FX map already exists; retain user edits')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.')[0] != SOURCE:
        raise RuntimeError('Start this script on the saved source-lighting map')
    source_file = package_file(SOURCE, '.umap')
    before = hashlib.sha256(source_file.read_bytes()).hexdigest()
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level = list(actors.get_all_level_actors())
    hero = next(a for a in level if a.get_actor_label() == 'HCZS_elsa')
    materials = apply_elsa_lighting_materials(hero)
    hero_component = hero.get_component_by_class(unreal.SkeletalMeshComponent)
    hero_component.set_editor_property('cast_shadow', True)
    settings = world.get_world_settings()
    settings.set_editor_property('force_no_precomputed_lighting', True)
    changed_lights = []
    for actor in level:
        for component in actor.get_components_by_class(unreal.LightComponent):
            previous = component.get_editor_property('intensity')
            component.set_mobility(unreal.ComponentMobility.MOVABLE)
            component.set_editor_property('intensity', 0.0)
            changed_lights.append({'label':actor.get_actor_label(), 'original_intensity':previous})
    light_specs = [
        ('HCZSPreviewWindowKey', -40, -30, 3.0, (1.0,.94,.85), True),
        ('HCZSPreviewCameraFill', -20, 150, .8, (.80,.89,1.0), False),
        ('HCZSPreviewRim', -25, 90, 1.0, (1.0,.85,.68), True),
    ]
    for index, (label, pitch, yaw, intensity, colour, shadow) in enumerate(light_specs):
        light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0,0,2000),
            unreal.Rotator(pitch=pitch,yaw=yaw,roll=0))
        light.set_actor_label(label)
        component = light.get_component_by_class(unreal.DirectionalLightComponent)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        component.set_editor_property('intensity', intensity)
        component.set_light_color(unreal.LinearColor(*colour,1))
        component.set_editor_property('cast_shadows', shadow)
        component.set_editor_property('light_source_angle', 2.0)
        component.set_editor_property('forward_shading_priority', 3-index)

    # An explicit lit preview of the original floor formula receives Elsa's
    # dynamic shadow. Other 65 source-lightmap bindings remain untouched.
    floor = next(a for a in level if a.get_actor_label() == 'furniture_floor')
    floor_component = floor.get_component_by_class(unreal.StaticMeshComponent)
    original_floor = floor_component.get_material(0)
    original_parent = original_floor.get_editor_property('parent')
    edit = unreal.MaterialEditingLibrary
    recipe = 'source-irradiance-floor-dynamic-35pct-v1'
    path = DEST + '/M_FloorDynamic'
    material = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if material:
        if unreal.EditorAssetLibrary.get_metadata_tag(material,'HczsDynamicPreviewRecipe') != recipe:
            raise RuntimeError('Unknown existing dynamic floor asset retained')
    else:
        material = unreal.EditorAssetLibrary.duplicate_asset(original_parent.get_path_name(), path)
        if not isinstance(material, unreal.Material):
            raise RuntimeError('Cannot copy the source floor shader')
        material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
        multiply = [n for n in edit.get_material_expressions(material) if isinstance(n, unreal.MaterialExpressionMultiply)]
        if len(multiply) != 1:
            raise RuntimeError('Reviewed source irradiance shader graph changed')
        irradiance = multiply[0]
        def scalar(value):
            node = edit.create_material_expression(material, unreal.MaterialExpressionConstant)
            node.set_editor_property('r', value)
            return node
        def weighted(value, property_id):
            node = edit.create_material_expression(material, unreal.MaterialExpressionMultiply)
            if not edit.connect_material_expressions(irradiance, '', node, 'A') or not edit.connect_material_expressions(scalar(value), '', node, 'B'):
                raise RuntimeError('Cannot connect dynamic floor weight')
            if not edit.connect_material_property(node, '', property_id):
                raise RuntimeError('Cannot connect dynamic floor output')
        weighted(.35, unreal.MaterialProperty.MP_BASE_COLOR)
        weighted(.65, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        edit.connect_material_property(scalar(.9), '', unreal.MaterialProperty.MP_ROUGHNESS)
        edit.connect_material_property(scalar(.12), '', unreal.MaterialProperty.MP_SPECULAR)
        edit.connect_material_property(scalar(0), '', unreal.MaterialProperty.MP_METALLIC)
        errors = list(edit.recompile_material(material))
        if errors: raise RuntimeError('Dynamic floor shader errors: '+repr(errors))
        unreal.EditorAssetLibrary.set_metadata_tag(material,'HczsDynamicPreviewRecipe',recipe)
        unreal.EditorAssetLibrary.save_loaded_asset(material,False)
    instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset('MI_FloorDynamic',DEST,
        unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    edit.set_material_instance_parent(instance, material)
    for name in ('SourceDiffuse','SourceLightmap'):
        texture = edit.get_material_instance_texture_parameter_value(original_floor, name)
        edit.set_material_instance_texture_parameter_value(instance, name, texture)
        if edit.get_material_instance_texture_parameter_value(instance, name) != texture:
            raise RuntimeError('Floor source texture binding failed')
    for name in ('LMUVScaleOffset','LMScale','LMAdd'):
        edit.set_material_instance_vector_parameter_value(instance,name,
            edit.get_material_instance_vector_parameter_value(original_floor,name))
    if not unreal.EditorAssetLibrary.save_loaded_asset(instance,False):
        raise RuntimeError('Cannot save floor preview')
    floor_component.set_material(0,instance)
    fx = apply_hall_sunlight(world)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world,TARGET):
        raise RuntimeError('Cannot save independent lighting/FX preview')
    after = hashlib.sha256(source_file.read_bytes()).hexdigest()
    if before != after: raise RuntimeError('Source lighting map changed')
    result = {'passed':True,'project':unreal.Paths.get_project_file_path(),'engine':unreal.SystemLibrary.get_engine_version(),
        'map':TARGET,'in_memory_world_after_saveas':world.get_path_name(),'source_map':SOURCE,'source_map_sha256_before':before,'source_map_sha256_after':after,
        'source_map_preserved':True,'hero_materials':len(materials['results']),'source_irradiance_maps':10,
        'source_irradiance_instances':66,'dynamic_floor_source':original_floor.get_path_name(),
        'dynamic_floor_policy':'.35 source irradiance as lit diffuse + .65 emissive; temporary UE shadow-receiver adaptation',
        'disabled_source_ue_lights':changed_lights,'preview_directional_lights':light_specs,
        'force_no_precomputed_lighting':settings.get_editor_property('force_no_precomputed_lighting'),
        'particle_components':fx['particle_component_count'],'original_shading_and_fx_equivalence_verified':False,
        'packaged_platforms_verified':False}
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    unreal.log('HCZS: independent lit Elsa and source sunlight preview saved: '+TARGET)


if __name__ == '__main__':
    main()
