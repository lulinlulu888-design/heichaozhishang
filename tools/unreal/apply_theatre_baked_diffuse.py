"""Apply source baked diffuse to unambiguous theatre instances in a new map."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/unreal/battle-reference/baked-diffuse'
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from repair_battle_visual_materials import node, link, prop, create_material, save_material

task = None
camera = None
result = None
handle = None
started = time.monotonic()
reflection_mode = '-HczsTheatreReflection' in u.SystemLibrary.get_command_line()
lit_surface = reflection_mode or '-HczsTheatreLitDiffuse' in u.SystemLibrary.get_command_line()
REPORT_PREFIX = 'reflection-' if reflection_mode else ('lit-' if lit_surface else '')
SCREEN_NAME = 'theatre-surface-reflection.png' if reflection_mode else ('theatre-surface-baked.png' if lit_surface else 'theatre-baked-diffuse.png')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply():
    recipe = json.loads((BASE / ('reflection-recipe.json' if reflection_mode else 'recipe.json')).read_text('utf8'))
    if lit_surface:
        recipe['sourceMap'] = '/Game/Recovered/SourceStages/Maps/L_TheatreSurface'
        recipe['targetMap'] = '/Game/Recovered/SourceStages/Maps/' + ('L_TheatreSurfaceReflection_' + recipe['recipeSha256'][:12] if reflection_mode else 'L_TheatreSurfaceBaked')
        for row in recipe['bindings']:
            row['actorLabel'] = row['actorLabel'].replace('boss_theatre_node_', 'boss_theatre_surface_node_')
    output = dict(recipeSha256=recipe['recipeSha256'], applied=[], deferred=recipe['deferred'],
        limitations=recipe['limitations'], nativeRenderVerified=False)
    cube = None
    if reflection_mode:
        cube = u.load_asset(recipe['reflectionCube'])
        if not isinstance(cube, u.TextureCube) or u.EditorAssetLibrary.get_metadata_tag(cube, 'HczsSourceDDS') != recipe['reflectionDdsSha256']:
            raise RuntimeError('Original reflection cube identity differs')
        output.update(reflectionCube=cube.get_path_name(), reflectionMaxMip=recipe['previewMaxMip'],
            reflectionInstanceCount=sum(row['reflectionWeight'] for row in recipe['bindings']))
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split('.')[0] != recipe['sourceMap']:
        raise RuntimeError('Start the editor in the original theatre inspection map')
    if u.EditorAssetLibrary.does_asset_exist(recipe['targetMap']):
        raise RuntimeError('Existing diffuse comparison map retained; use readback instead')
    source_file = ROOT / 'clients/unreal5 5.8/Content' / (recipe['sourceMap'].removeprefix('/Game/') + '.umap')
    before = digest(source_file)
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    by_label = {a.get_actor_label(): a for a in actors}
    mesh_tools = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    verified = []
    for row in recipe['bindings']:
        if row['actorLabel'] not in by_label:
            raise RuntimeError('Source instance missing: ' + row['actorLabel'])
        component = by_label[row['actorLabel']].get_component_by_class(u.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh') if component else None
        if not mesh or mesh.get_num_sections(0) != 1 or component.get_num_materials() != 1:
            raise RuntimeError('Source single-primitive/native section mapping differs')
        channels = mesh_tools.get_num_uv_channels(mesh, 0)
        build = mesh_tools.get_lod_build_settings(mesh, 0)
        if channels < 2 or (build.get_editor_property('generate_lightmap_u_vs') and
                             build.get_editor_property('dst_lightmap_index') == 1):
            raise RuntimeError('Original source UV1 missing or replaced by generated UVs')
        verified.append((row, component, mesh.get_path_name(), channels))
    destination = '/Game/Recovered/SourceStages/TheatreBakedDiffuse/' + ('Reflection_' if reflection_mode else ('Lit_' if lit_surface else 'v_')) + recipe['recipeSha256'][:16]
    plan = dict(destination=destination, recipe_sha256=recipe['recipeSha256'])
    textures = {}
    for key, row in recipe['images'].items():
        if digest(Path(row['path'])) != row['sha256']:
            raise RuntimeError('Decoded texture bytes changed')
        name = 'T_' + key[:20] + ('_Color' if row['srgb'] else '_Linear')
        path = destination + '/' + name
        texture = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
        if texture:
            if u.EditorAssetLibrary.get_metadata_tag(texture, 'HczsSourcePNG') != row['sha256']:
                raise RuntimeError('Texture namespace contains unrelated data')
        else:
            request = u.AssetImportTask()
            for field, value in dict(filename=row['path'], destination_path=destination, destination_name=name,
                automated=True, replace_existing=False, save=False).items(): request.set_editor_property(field, value)
            u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([request])
            imported = request.get_objects()
            if len(imported) != 1 or not isinstance(imported[0], u.Texture2D):
                raise RuntimeError('Texture import failed')
            texture = imported[0]
        texture.set_editor_property('srgb', row['srgb'])
        is_normal = lit_surface and any(b['normal'] == key for b in recipe['bindings'])
        compression = u.TextureCompressionSettings.TC_NORMALMAP if is_normal else (u.TextureCompressionSettings.TC_DEFAULT if row['srgb'] else u.TextureCompressionSettings.TC_HDR)
        texture.set_editor_property('compression_settings', compression)
        texture.set_editor_property('filter', u.TextureFilter.TF_BILINEAR)
        texture.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        texture.set_editor_property('never_stream', True)
        if any(b['lightmap'] == key for b in recipe['bindings']):
            texture.set_editor_property('address_x', u.TextureAddress.TA_CLAMP)
            texture.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
        u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourcePNG', row['sha256'])
        if not u.EditorAssetLibrary.save_loaded_asset(texture, False):
            raise RuntimeError('Texture save failed')
        textures[key] = texture
    for row, component, mesh_path, channels in verified:
        material, build = create_material(u, plan, 'M_' + row['uuid'].replace('-', ''), 'OPAQUE')
        if build:
            if lit_surface:
                material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
            custom = node(u, material, u.MaterialExpressionCustom, 0, 0,
                code=recipe['shader'], output_type=u.CustomMaterialOutputType.CMOT_FLOAT3,
                description='APK UE4_lm decoded baked diffuse only')
            names = ['UV0', 'UV1', 'Albedo', 'Mix', 'Lightmap', 'UVScaleOffset', 'LMScale', 'LMAdd']
            if reflection_mode:
                names += ['SourceProbe', 'ReflectionDirectionUE', 'WorldNormal', 'ViewDirectionUE', 'MaxMip', 'ReflectionWeight']
            inputs = []
            for name in names:
                pin = u.CustomInput(); pin.set_editor_property('input_name', name); inputs.append(pin)
            custom.set_editor_property('inputs', inputs)
            for channel in (0, 1):
                uv = node(u, material, u.MaterialExpressionTextureCoordinate, -650, channel * 100, coordinate_index=channel)
                link(u, uv, '', custom, 'UV' + str(channel))
            for i, (name, key) in enumerate([('Albedo', row['albedo']), ('Mix', row['mix']), ('Lightmap', row['lightmap'])]):
                texture = node(u, material, u.MaterialExpressionTextureObject, -650, 250 + i * 130,
                    texture=textures[key], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR if recipe['images'][key]['srgb'] else u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                link(u, texture, '', custom, name)
            for i, (name, values) in enumerate([('UVScaleOffset', row['uvScaleOffset']), ('LMScale', row['lmScale'] + [0]), ('LMAdd', row['lmAdd'] + [0])]):
                value = node(u, material, u.MaterialExpressionVectorParameter, -1000, 100 + i * 150,
                    parameter_name=name, default_value=u.LinearColor(*values))
                link(u, value, 'RGBA' if name == 'UVScaleOffset' else 'RGB', custom, name)
            if reflection_mode:
                probe = node(u, material, u.MaterialExpressionTextureObject, -650, 800,
                    texture=cube, sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                link(u, probe, '', custom, 'SourceProbe')
                for i, (name, cls) in enumerate([
                        ('ReflectionDirectionUE', u.MaterialExpressionReflectionVectorWS),
                        ('WorldNormal', u.MaterialExpressionPixelNormalWS),
                        ('ViewDirectionUE', u.MaterialExpressionCameraVectorWS)]):
                    value = node(u, material, cls, -1000, 700 + i*100)
                    link(u, value, '', custom, name)
                for i, (name, value) in enumerate([('MaxMip', recipe['previewMaxMip']), ('ReflectionWeight', row['reflectionWeight'])]):
                    scalar = node(u, material, u.MaterialExpressionConstant, -1000, 1050 + i*100, r=float(value))
                    link(u, scalar, '', custom, name)
            prop(u, custom, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
            if lit_surface:
                albedo = node(u, material, u.MaterialExpressionTextureSample, -650, -200,
                    texture=textures[row['albedo']], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR)
                mix = node(u, material, u.MaterialExpressionTextureSample, -650, -400,
                    texture=textures[row['mix']], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                normal = node(u, material, u.MaterialExpressionTextureSample, -650, -600,
                    texture=textures[row['normal']], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL)
                prop(u, albedo, 'RGB', u.MaterialProperty.MP_BASE_COLOR)
                prop(u, mix, 'G', u.MaterialProperty.MP_ROUGHNESS)
                prop(u, mix, 'B', u.MaterialProperty.MP_METALLIC)
                prop(u, mix, 'R', u.MaterialProperty.MP_AMBIENT_OCCLUSION)
                prop(u, normal, 'RGB', u.MaterialProperty.MP_NORMAL)
            save_material(u, material, plan)
        old = component.get_material(0).get_path_name()
        component.set_material(0, material)
        output['applied'].append(dict(uuid=row['uuid'], actor=row['actorLabel'], mesh=mesh_path,
            sourceUvChannels=channels, originalMaterial=old, derivedMaterial=material.get_path_name()))
    camera = by_label.get('HCZSSourceStageCamera')
    if not camera or not u.EditorLoadingAndSavingUtils.save_map(world, recipe['targetMap']):
        raise RuntimeError('Cannot save independent comparison map')
    if digest(source_file) != before:
        raise RuntimeError('Original inspection map changed')
    output.update(map=recipe['targetMap'], sourceMapUnchanged=True, sourceMapSha256=before)
    (BASE / (REPORT_PREFIX + 'native-apply.json')).write_text(json.dumps(output, indent=2), 'utf8')
    return camera, output


def tick(delta):
    global task
    try:
        if time.monotonic() - started > 120:
            raise RuntimeError('Screenshot deadline exceeded')
        if task is None and time.monotonic() - started > 10:
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 720,
                str(BASE / SCREEN_NAME), camera=camera, delay=1)
        elif task is not None and task.is_task_done():
            path = BASE / SCREEN_NAME
            if not path.is_file() or path.stat().st_size < 10000:
                raise RuntimeError('Screenshot missing')
            result.update(nativeRenderVerified=True, screenshot=str(path), screenshotSha256=digest(path))
            (BASE / (REPORT_PREFIX + 'native-render.json')).write_text(json.dumps(result, indent=2), 'utf8')
            u.unregister_slate_post_tick_callback(handle)
            u.SystemLibrary.quit_editor()
    except Exception:
        (BASE / 'error.txt').write_text(traceback.format_exc(), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


try:
    previous_error = BASE / 'error.txt'
    if previous_error.exists():
        previous_error.rename(BASE / ('error-' + str(time.time_ns()) + '.txt'))
    camera, result = apply()
    started = time.monotonic()
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    (BASE / 'error.txt').write_text(traceback.format_exc(), 'utf8')
    u.SystemLibrary.quit_editor()
