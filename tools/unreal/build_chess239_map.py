"""Build the original prologue worldline chess map (scene 239, map 50002) in UE.

Run in the full editor with -ExecCmds="py <this file>"; UE 5.8 closes the
editor as soon as an -ExecutePythonScript script returns, before the
screenshot tick can finish.
Inputs are pinned derived exports of the APK: chess_xuzhang geometry/Tex0,
its UE4_lm lightmaps, map-piece models and cell-ring SFX sprites.  Elsa, her
weapon and idle are reused from the verified tutorial battle map.  Output is
limited to /Game/Recovered/Worldline/Chess239 and the L_Chess239 map.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback
import xml.etree.ElementTree as ET

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from export_elsa_model import split_glb, pack_glb
from import_recovered_assets import make_pipeline

OUT = ROOT / 'analysis/unreal/worldline-chess'
SCENE_GLB = ROOT / 'analysis/battle-visual/scene-export/prologue-scene.glb'
SCENE_SHA = '60c2e4082772918c4493e3d2fdd21d4ea35b441e374467dcb7aace40717ed8e4'
LIGHTMAPS = ROOT / 'analysis/battle-visual/lightmaps/bindings.json'
PIECES = ROOT / 'analysis/mainline-dungeon/pieces/report.json'
CELL_FX = ROOT / 'analysis/mainline-dungeon/cell-fx/recipe.json'
SCENES = ROOT / 'analysis/mainline-dungeon/data/scenes.json'
SCENE_XML = ROOT / 'analysis/battle-visual/scene-00220.bin'
SCENE_XML_SHA = '410761fae3aee0b8c67e9505831942d99eafb1dfa3380ea1a2e3699c963d53f7'
MAP_JSON = ROOT / 'analysis/mainline-dungeon/data/map50002.json'
DEST = '/Game/Recovered/Worldline/Chess239'
MAP = '/Game/Recovered/Worldline/Maps/L_Chess239'
TUTORIAL = '/Game/Recovered/Battle/Maps/L_TutorialSource2133'
# iMapScene.calculatePiecePos for map 50002 cells; initMapPiece passes the key's first
# number as x (tools/audit_map_scene_center.py).  Height is the scene centre y.
CELLS = {'21,22': (-189.0, 344.548), '20,22': (-189.0, 316.836), '19,22': (-189.0, 289.124)}
CELL_Y = 16.26
# ResolutionConst.ML_DUNGEON_CAMERA_TO_CHESS_RANGE_WHEN_CLICK = (-100, 135.5, 142.2) / 1.5
CAMERA_RELATIVE = (-100 / 1.5, 135.5 / 1.5, 142.2 / 1.5)
LM_CODE = '''float3 encoded = Texture2DSample(Lightmap, LightmapSampler, UV1 * UVScaleOffset.xy + UVScaleOffset.zw).rgb * LMScale + LMAdd;
float logL = dot(float3(0.299, 0.587, 0.114), encoded);
float luminance = (exp2(logL * 16.0 - 8.0) - 0.00390625) * 0.6;
return Texture2DSample(Albedo, AlbedoSampler, UV0).rgb * encoded * (luminance / max(logL, 0.00001));'''
FX_CODE = '''float t = frac(Time / max(Life, 0.001));
float4 c = K0;
if (Count > 1.5 && t >= T.x) c = lerp(K0, K1, saturate((t - T.x) / max(T.y - T.x, 1e-4)));
if (Count > 1.5 && t >= T.y) c = K1;
if (Count > 2.5 && t >= T.y) c = lerp(K1, K2, saturate((t - T.y) / max(T.z - T.y, 1e-4)));
if (Count > 2.5 && t >= T.z) c = K2;
if (Count > 3.5 && t >= T.z) c = lerp(K2, K3, saturate((t - T.z) / max(T.w - T.z, 1e-4)));
if (Count > 3.5 && t >= T.w) c = K3;
if (Count > 4.5 && t >= T.w) c = lerp(K3, K4, saturate((t - T.w) / max(T4 - T.w, 1e-4)));
if (Count > 4.5 && t >= T4) c = K4;
return c;'''

results = {}
handle = None
started = time.monotonic()
camera = None
task = None
stage = 0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def node(material, kind, x, y, **properties):
    obj = u.MaterialEditingLibrary.create_material_expression(material, kind, x, y)
    check(obj is not None, 'Cannot create material expression')
    for key, value in properties.items():
        obj.set_editor_property(key, value)
    return obj


def link(source, output, target, name):
    check(u.MaterialEditingLibrary.connect_material_expressions(source, output, target, name), 'Material link failed ' + name)


def custom(material, code, names, output_type, x=0, y=0):
    expr = node(material, u.MaterialExpressionCustom, x, y, code=code, output_type=output_type)
    pins = []
    for name in names:
        pin = u.CustomInput()
        pin.set_editor_property('input_name', name)
        pins.append(pin)
    expr.set_editor_property('inputs', pins)
    return expr


def exposure_free_emissive(material, source, output):
    inverse = node(material, u.MaterialExpressionEyeAdaptationInverse, 450, -100)
    one = node(material, u.MaterialExpressionConstant, 200, -300, r=1.0)
    names = [str(n) for n in u.MaterialEditingLibrary.get_material_expression_input_names(inverse)]
    pin = lambda prefix: next(n for n in names if ''.join(c for c in n.lower() if c.isalnum()).startswith(prefix))
    link(source, output, inverse, pin('lightvalue'))
    link(one, '', inverse, pin('alpha'))
    check(u.MaterialEditingLibrary.connect_material_property(inverse, '', u.MaterialProperty.MP_EMISSIVE_COLOR), 'Emissive link failed')


def new_material(name, blend):
    material = u.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST, u.Material, u.MaterialFactoryNew())
    check(material is not None, 'Cannot create ' + name)
    material.set_editor_property('blend_mode', blend)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property('two_sided', True)
    return material


def finish_material(material):
    errors = u.MaterialEditingLibrary.recompile_material(material)
    check(errors is not None and not list(errors), 'Material compile failed: ' + repr(list(errors or [])))
    check(u.EditorAssetLibrary.save_loaded_asset(material, False), 'Material save failed')


def lightmap_parent(default_texture):
    material = new_material('M_ChessLightmap', u.BlendMode.BLEND_OPAQUE)
    expr = custom(material, LM_CODE, ['UV0', 'UV1', 'Albedo', 'Lightmap', 'UVScaleOffset', 'LMScale', 'LMAdd'],
                  u.CustomMaterialOutputType.CMOT_FLOAT3)
    for channel in (0, 1):
        link(node(material, u.MaterialExpressionTextureCoordinate, -650, channel * 100, coordinate_index=channel), '', expr, 'UV' + str(channel))
    for i, (name, sampler) in enumerate([('Albedo', u.MaterialSamplerType.SAMPLERTYPE_COLOR),
                                          ('Lightmap', u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)]):
        param = node(material, u.MaterialExpressionTextureObjectParameter, -650, 250 + i * 150,
                     parameter_name=name, texture=default_texture, sampler_type=sampler)
        link(param, '', expr, name)
    for i, name in enumerate(('UVScaleOffset', 'LMScale', 'LMAdd')):
        param = node(material, u.MaterialExpressionVectorParameter, -1000, 100 + i * 150, parameter_name=name)
        link(param, 'RGBA' if name == 'UVScaleOffset' else 'RGB', expr, name)
    exposure_free_emissive(material, expr, '')
    # The baked term stays emissive; the scene's dynamic dir_light lights the albedo and casts character shadows.
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
    albedo = node(material, u.MaterialExpressionTextureSampleParameter2D, -650, -300, parameter_name='Albedo', texture=default_texture)
    check(u.MaterialEditingLibrary.connect_material_property(albedo, 'RGB', u.MaterialProperty.MP_BASE_COLOR), 'Base colour link failed')
    for prop, value in ((u.MaterialProperty.MP_SPECULAR, 0.0), (u.MaterialProperty.MP_ROUGHNESS, 1.0)):
        check(u.MaterialEditingLibrary.connect_material_property(node(material, u.MaterialExpressionConstant, -300, -500, r=value), '', prop),
              'Surface constant link failed')
    finish_material(material)
    return material


def fx_parent(name, blend, default_texture):
    material = new_material(name, blend)
    color = custom(material, FX_CODE, ['Time', 'Life', 'Count', 'T', 'T4', 'K0', 'K1', 'K2', 'K3', 'K4'],
                   u.CustomMaterialOutputType.CMOT_FLOAT4, -400, 0)
    link(node(material, u.MaterialExpressionTime, -800, -100), '', color, 'Time')
    for i, key in enumerate(('Life', 'Count', 'T4')):
        link(node(material, u.MaterialExpressionScalarParameter, -800, i * 80, parameter_name=key), '', color, key)
    link(node(material, u.MaterialExpressionVectorParameter, -800, 250, parameter_name='T'), 'RGBA', color, 'T')
    for i in range(5):
        link(node(material, u.MaterialExpressionVectorParameter, -800, 400 + i * 120, parameter_name='K' + str(i)), 'RGBA', color, 'K' + str(i))
    texture = node(material, u.MaterialExpressionTextureSampleParameter2D, -400, 400, parameter_name='Sprite', texture=default_texture)
    color_rgb = node(material, u.MaterialExpressionComponentMask, -250, 100, r=True, g=True, b=True, a=False)
    link(color, '', color_rgb, '')
    rgb = node(material, u.MaterialExpressionMultiply, -100, 200)
    link(texture, 'RGB', rgb, 'A'); link(color_rgb, '', rgb, 'B')
    alpha_tex = node(material, u.MaterialExpressionComponentMask, -100, 500, r=False, g=False, b=False, a=True)
    link(texture, 'RGBA', alpha_tex, '')
    alpha_key = node(material, u.MaterialExpressionComponentMask, -100, 600, r=False, g=False, b=False, a=True)
    link(color, '', alpha_key, '')
    alpha = node(material, u.MaterialExpressionMultiply, 100, 550)
    link(alpha_tex, '', alpha, 'A'); link(alpha_key, '', alpha, 'B')
    if blend == u.BlendMode.BLEND_ADDITIVE:
        premul = node(material, u.MaterialExpressionMultiply, 200, 300)
        link(rgb, '', premul, 'A'); link(alpha, '', premul, 'B')
        rgb3 = node(material, u.MaterialExpressionComponentMask, 300, 300, r=True, g=True, b=True, a=False)
        link(premul, '', rgb3, '')
        exposure_free_emissive(material, rgb3, '')
    else:
        rgb3 = node(material, u.MaterialExpressionComponentMask, 300, 300, r=True, g=True, b=True, a=False)
        link(rgb, '', rgb3, '')
        exposure_free_emissive(material, rgb3, '')
        check(u.MaterialEditingLibrary.connect_material_property(alpha, '', u.MaterialProperty.MP_OPACITY), 'Opacity link failed')
    finish_material(material)
    return material


def import_texture(path, name, srgb, clamp=False):
    request = u.AssetImportTask()
    for field, value in dict(filename=str(path), destination_path=DEST + '/Textures', destination_name=name,
                             automated=True, replace_existing=False, save=False).items():
        request.set_editor_property(field, value)
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([request])
    objects = request.get_objects()
    check(len(objects) == 1 and isinstance(objects[0], u.Texture2D), 'Texture import failed: ' + str(path))
    texture = objects[0]
    texture.set_editor_property('srgb', srgb)
    texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_DEFAULT if srgb else u.TextureCompressionSettings.TC_HDR)
    if clamp:
        texture.set_editor_property('address_x', u.TextureAddress.TA_CLAMP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
    u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourcePNG', digest(path))
    check(u.EditorAssetLibrary.save_loaded_asset(texture, False), 'Texture save failed')
    return texture


def instance(parent, name, scalars=None, vectors=None, textures=None):
    factory = u.MaterialInstanceConstantFactoryNew()
    mi = u.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST + '/Instances', u.MaterialInstanceConstant, factory)
    check(mi is not None, 'Cannot create instance ' + name)
    u.MaterialEditingLibrary.set_material_instance_parent(mi, parent)
    for key, value in (scalars or {}).items():
        u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, key, float(value))
    for key, value in (vectors or {}).items():
        u.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, key, u.LinearColor(*value))
    for key, value in (textures or {}).items():
        u.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi, key, value)
    u.MaterialEditingLibrary.update_material_instance(mi)
    check(u.EditorAssetLibrary.save_loaded_asset(mi, False), 'Instance save failed')
    return mi


def import_static_mesh(glb, name):
    pipeline, overrides = make_pipeline(u, {'import_operation': 'asset'})
    parameters = u.ImportAssetParameters()
    parameters.set_editor_property('is_automated', True)
    parameters.set_editor_property('replace_existing', False)
    parameters.set_editor_property('override_pipelines', overrides)
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    destination = DEST + '/Pieces/' + name
    check(manager.import_asset(destination, u.InterchangeManager.create_source_data(str(glb)), parameters), 'Piece import failed')
    meshes = [a for a in u.EditorAssetLibrary.list_assets(destination, True, False)
              if isinstance(u.load_asset(a), u.StaticMesh)]
    check(len(meshes) == 1, 'Expected one piece mesh: ' + name)
    for asset in u.EditorAssetLibrary.list_assets(destination, True, False):
        u.EditorAssetLibrary.save_asset(asset, only_if_is_dirty=False)
    return u.load_asset(meshes[0])


def source_to_adapter(x, y, z):
    return u.Vector(x * 100, z * 100, y * 100)


def source_dir_light():
    raw = SCENE_XML.read_bytes()
    check(digest(SCENE_XML) == SCENE_XML_SHA, 'Chess scene XML changed')
    root = ET.fromstring(raw)
    enabled = [l for l in root.find('Scene/Global').findall('Lights/light') if l.get('Enable') == 'true']
    check([l.get('Name') for l in enabled] == ['dir_light', 'shadow_light'], 'Chess light inventory changed')
    sun = enabled[0]
    check(sun.get('Type') == '3' and sun.get('RenderCondition') == '0', 'dir_light type changed')
    floats = lambda text: [float(v) for v in text.split(',')]
    return dict(name='dir_light', direction=floats(sun.get('Direction')), intensity=float(sun.get('Intensity')),
                colour=floats(sun.find('Diffuse/Key_0').get('Color')), excluded='shadow_light Intensity 0')


def build():
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    check(digest(SCENE_GLB) == SCENE_SHA, 'Prologue scene export changed')
    lightmaps = json.loads(LIGHTMAPS.read_text('utf8'))
    pieces = json.loads(PIECES.read_text('utf8'))
    cell_fx = json.loads(CELL_FX.read_text('utf8'))
    scene = next(r for r in json.loads(SCENES.read_text('utf8'))['rows'] if r['id'] == 239)['fields']
    game_map = json.loads(MAP_JSON.read_text('utf8'))['data']
    check(scene['ScenePath'] == 'scene/chess_xuzhang/chess_xuzhang.scn' and scene['DefaultCamera'] == 'camera_1', 'Scene 239 changed')
    check(sorted(game_map['MapData']) == sorted(CELLS), 'Map 50002 cells changed')
    # Derived output only; remove Content/Recovered/Worldline/{Chess239,Maps/L_Chess239.umap} on disk to rebuild.
    check(not u.EditorAssetLibrary.does_asset_exist(MAP) and not u.EditorAssetLibrary.list_assets(DEST, True, False),
          'Chess map output already exists')

    # Elsa template from the verified battle map.
    world = u.EditorLoadingAndSavingUtils.load_map(TUTORIAL)
    check(world is not None, 'Cannot load tutorial template map')
    by_tag = lambda tag: [a for a in actors.get_all_level_actors() if a.actor_has_tag(tag)]
    player, weapon, presentation = by_tag('HCZSBattlePlayer'), by_tag('HCZSBattleWeapon'), by_tag('HCZSBattlePresentation')
    check(len(player) == len(weapon) == len(presentation) == 1, 'Tutorial template actors differ')
    pc = player[0].get_component_by_class(u.SkeletalMeshComponent)
    wc = weapon[0].get_component_by_class(u.StaticMeshComponent)
    animations = presentation[0].get_editor_property('SceneAssets').get_editor_property('player_animations')
    check('idle_1' in animations, 'Elsa idle_1 missing')
    template = dict(mesh=pc.get_skeletal_mesh_asset(), materials=[pc.get_material(i) for i in range(pc.get_num_materials())],
                    scale=player[0].get_actor_relative_scale3d(), idle=animations['idle_1'],
                    weapon=wc.get_editor_property('static_mesh'), weaponMaterials=[wc.get_material(i) for i in range(wc.get_num_materials())],
                    socket=wc.get_attach_socket_name(), weaponRelative=wc.get_relative_transform())

    world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
    raw = SCENE_GLB.read_bytes()
    document, binary = split_glb(raw)
    for number, entry in enumerate(document['nodes']):
        entry['name'] = 'chess239_node_' + str(number)
    OUT.mkdir(parents=True, exist_ok=True)
    staged = OUT / 'chess239-import.glb'
    staged.write_bytes(pack_glb(document, binary))
    pipeline, overrides = make_pipeline(u, {'import_operation': 'scene'})
    parameters = u.ImportAssetParameters()
    parameters.set_editor_property('is_automated', True)
    parameters.set_editor_property('replace_existing', False)
    parameters.set_editor_property('override_pipelines', overrides)
    parameters.set_editor_property('import_level', u.EditorLevelUtils.get_levels(world)[0])
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    check(manager.import_scene(DEST + '/Scene', u.InterchangeManager.create_source_data(str(staged)), parameters), 'Scene import failed')
    spatial = list(actors.get_all_level_actors())
    adapter = actors.spawn_actor_from_class(u.Actor, u.Vector())
    adapter.set_actor_label('HCZSChessAxisAdapter')
    adapter.get_editor_property('root_component').set_mobility(u.ComponentMobility.STATIC)
    for actor in spatial:
        if actor.get_editor_property('root_component') and actor.get_attach_parent_actor() is None:
            actor.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_WORLD, u.AttachmentRule.KEEP_WORLD, u.AttachmentRule.KEEP_WORLD, False)
    adapter.set_actor_scale3d(u.Vector(-1, 1, 1))
    labels = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
    # The scene file carries an editor ailisha_1565 placeholder one row behind the start
    # cell; the runtime avatar replaces it and the reference frame shows only one Elsa.
    placeholders = []
    for number, entry in enumerate(document['nodes']):
        if 'mesh' in entry and document['meshes'][entry['mesh']].get('name', '').startswith('character/'):
            actor = labels['chess239_node_' + str(number)]
            actor.set_actor_hidden_in_game(True)
            actor.set_is_temporarily_hidden_in_editor(True)
            actor.get_component_by_class(u.StaticMeshComponent).set_visibility(False)
            placeholders.append(entry['extras']['sourceInstance']['Name'])
    results['hiddenPlaceholders'] = placeholders

    # Original UE4_lm lightmaps on bound opaque instances.
    lm_textures = {}
    for index, decoded in enumerate(lightmaps['decoded_images']):
        png = ROOT / decoded['outputs'][0]['png']
        lm_textures[index] = import_texture(png, 'T_ChessLightmap_' + str(index), False, True)
    lm_parent = lightmap_parent(lm_textures[0])
    by_uuid = {n['extras']['sourceInstance']['UUID']: i for i, n in enumerate(document['nodes'])}
    applied, skipped = 0, []
    for binding in lightmaps['bindings']:
        index = by_uuid.get(binding['uuid'])
        actor = labels.get('chess239_node_' + str(index)) if index is not None else None
        component = actor.get_component_by_class(u.StaticMeshComponent) if actor else None
        if not component or component.get_num_materials() != 1:
            skipped.append(dict(uuid=binding['uuid'], reason='no single-section actor'))
            continue
        original = component.get_material(0)
        names = [str(n) for n in u.MaterialEditingLibrary.get_texture_parameter_names(original)] if isinstance(original, u.MaterialInstance) else []
        albedo_name = next((n for n in names if 'basecolor' in n.lower().replace('_', '')), None)
        albedo = u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(original, albedo_name) if albedo_name else None
        material = document['materials'][document['meshes'][document['nodes'][index]['mesh']]['primitives'][0]['material']]
        if albedo is None or material.get('alphaMode', 'OPAQUE') != 'OPAQUE':
            skipped.append(dict(uuid=binding['uuid'], reason='non-opaque or albedo parameter missing', parameters=names))
            continue
        p = binding['parameters']
        check(p['encode_type'] == '4' and p['UE4_lm'] == 'true', 'Unsupported lightmap encoding')
        vec = lambda key: [float(v) for v in p[key].split(',')]
        mi = instance(lm_parent, 'MI_LM_' + binding['uuid'].replace('-', ''),
                      vectors=dict(UVScaleOffset=vec('uv_scale') + vec('uv_ofs'), LMScale=vec('lightmap_scale') + [0],
                                   LMAdd=vec('lightmap_add')[:3] + [0]),
                      textures=dict(Albedo=albedo, Lightmap=lm_textures[int(p['texture_index'])]))
        component.set_material(0, mi)
        applied += 1
    results['lightmaps'] = dict(bindings=len(lightmaps['bindings']), applied=applied, skipped=skipped)

    # Cell ring SFX sprites and the selected level-cell emblem.
    plane = u.load_asset('/Engine/BasicShapes/Plane.Plane')
    sprite_textures = {k: import_texture(ROOT / v['png'], 'T_' + Path(k).stem, True, True) for k, v in cell_fx['textures'].items()}
    default_sprite = next(iter(sprite_textures.values()))
    fx_parents = {'add': fx_parent('M_CellFxAdditive', u.BlendMode.BLEND_ADDITIVE, default_sprite),
                  'blend': fx_parent('M_CellFxTranslucent', u.BlendMode.BLEND_TRANSLUCENT, default_sprite)}
    start = next(k for k, v in game_map['MapData'].items() if v.get('isStartPos'))
    first = next(k for k, v in game_map['MapData'].items() if v.get('levelID') == 3997)
    states = [(start, 'zq_suozai', 'HCZSChessPlayerCell'), (first, 'zq_xuanzhong', 'HCZSChessSelectedCell')]
    spawned = []
    for cell, model, tag in states:
        x, z = CELLS[cell]
        effect = cell_fx['effects'][model]
        for number, sprite in enumerate(effect['sprites']):
            keys = sprite['colorKeysArgb'][:5]
            check(keys, 'Sprite has no colour key')
            argb = lambda k: [k['value'][1] / 255, k['value'][2] / 255, k['value'][3] / 255, k['value'][0] / 255]
            colours = [argb(k) for k in keys] + [argb(keys[-1])] * (5 - len(keys))
            times = [k['time'] for k in keys] + [keys[-1]['time']] * (5 - len(keys))
            mi = instance(fx_parents['blend' if sprite['blendMode'] == 0 else 'add'],
                          'MI_' + model + '_' + str(number),
                          scalars=dict(Life=sprite['lifeSpan'], Count=len(keys), T4=times[4]),
                          vectors=dict(T=times[:4], **{'K' + str(i): colours[i] for i in range(5)}),
                          textures=dict(Sprite=sprite_textures[sprite['texture']]))
            ox, oy, oz = sprite['posOffset']
            scale = effect['socketScale']
            actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
            actor.set_actor_label(tag + '_' + str(number))
            actor.set_editor_property('tags', [tag])
            component = actor.get_component_by_class(u.StaticMeshComponent)
            component.set_mobility(u.ComponentMobility.MOVABLE)
            component.set_static_mesh(plane)
            component.set_material(0, mi)
            component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            component.set_editor_property('cast_shadow', False)
            component.set_editor_property('translucency_sort_priority', 10 + sprite['renderBias'])
            actor.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, False)
            # Plane is 100 UE units; sprite edge is 2*Radius source units.  Texture
            # vertices (pointy v) align with the source hexagon's x-axis vertices.
            size = 2 * sprite['radius'] * scale
            actor.set_actor_relative_location(source_to_adapter(x + ox * scale, CELL_Y + 0.58 + 0.05 * number, z + oz * scale), False, False)
            actor.set_actor_relative_rotation(u.Rotator(pitch=0, yaw=90 + sprite['yawDegrees'], roll=0), False, False)
            actor.set_actor_relative_scale3d(u.Vector(size, size, 1))
            spawned.append(dict(tag=tag, cell=cell, model=model, sprite=sprite['name'], blendMode=sprite['blendMode']))
    piece = pieces['pieces'][str(game_map['Global']['normalMPieceId'])]
    emblem_mesh = import_static_mesh(ROOT / pieces['models'][piece['ResUpper']]['glb'], 'Emblem')
    emblem = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
    emblem.set_actor_label('HCZSChessSelectedEmblem')
    emblem.set_editor_property('tags', ['HCZSChessSelectedEmblem'])
    component = emblem.get_component_by_class(u.StaticMeshComponent)
    component.set_mobility(u.ComponentMobility.MOVABLE)
    component.set_static_mesh(emblem_mesh)
    component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow', False)
    emblem.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, False)
    x, z = CELLS[first]
    s = piece['ResUpper_Scale'][0]
    emblem.set_actor_relative_location(source_to_adapter(x, CELL_Y + piece['ResUpper_Pos'] + 29, z), False, False)
    emblem.set_actor_relative_rotation(u.Rotator(pitch=0, yaw=-math.degrees(scene['Icon_Rotate'][1]), roll=0), False, False)
    emblem.set_actor_relative_scale3d(u.Vector(s, s, s))

    # Elsa on the start cell.  Selecting 3997 runs faceToNewChallenge -> faceToDirection:
    # rotY = acos(d . (0,0,1) / |d|), negated when d.x < 0 (PlayerOrientation is the unselected pose).
    x, z = CELLS[start]
    fx, fz = CELLS[first][0] - x, CELLS[first][1] - z
    face_y = math.acos(fz / math.hypot(fx, fz)) * (1 if fx >= 0 else -1)
    elsa = actors.spawn_actor_from_class(u.SkeletalMeshActor, u.Vector())
    elsa.set_actor_label('HCZSChessPlayer')
    elsa.set_editor_property('tags', ['HCZSChessPlayer'])
    elsa.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, False)
    elsa.set_actor_relative_location(source_to_adapter(x, CELL_Y, z), False, False)
    # Source rotY 0 faces +z; under the mirrored adapter the imported battle mesh needs a half turn
    # (yaw probe: rotY pi -> yaw 0 shows her back with the sword toward 3997, as in the reference).
    elsa.set_actor_relative_rotation(u.Rotator(pitch=0, yaw=180 - math.degrees(face_y), roll=0), False, False)
    elsa.set_actor_relative_scale3d(template['scale'])
    sk = elsa.get_component_by_class(u.SkeletalMeshComponent)
    sk.set_skeletal_mesh_asset(template['mesh'])
    for index, material in enumerate(template['materials']):
        sk.set_material(index, material)
    sk.override_animation_data(template['idle'], True, True, 0., 1.)
    sk.set_update_animation_in_editor(True)
    sk.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    sk.set_editor_property('cast_shadow', True)
    sword = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
    sword.set_actor_label('HCZSChessPlayerWeapon')
    swc = sword.get_component_by_class(u.StaticMeshComponent)
    swc.set_mobility(u.ComponentMobility.MOVABLE)
    swc.set_static_mesh(template['weapon'])
    for index, material in enumerate(template['weaponMaterials']):
        swc.set_material(index, material)
    swc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    check(swc.attach_to_component(sk, template['socket'], u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE,
                                  u.AttachmentRule.KEEP_RELATIVE, False), 'Cannot attach weapon')
    swc.set_relative_transform(template['weaponRelative'], False, True)

    # camMoveToChess(isEnterGrid, limit=False): player cell + RealtivePos / 1.5 without the
    # CameraRange clamp; camera_1 rotation, vertical FOV 30.  The reference frame centres the player cell.
    source_camera = next(c for c in json.loads((ROOT / 'analysis/battle-visual/scene-export/report.json').read_text('utf8'))['limitations']['sourceCameras']
                         if c['Name'] == scene['DefaultCamera'])
    m = [float(v) for v in source_camera['Transform'].split(',')]
    to_ue = lambda v: u.Vector(-v[0], v[2], v[1])
    forward, up = to_ue(m[8:11]), to_ue(m[4:7])
    cx, cz = CELLS[start]
    position = [cx + CAMERA_RELATIVE[0], CELL_Y + CAMERA_RELATIVE[1], cz + CAMERA_RELATIVE[2]]
    cam = actors.spawn_actor_from_class(u.CameraActor, u.Vector(-position[0] * 100, position[2] * 100, position[1] * 100),
                                        u.MathLibrary.make_rot_from_xz(forward, up))
    cam.set_actor_label('HCZSDungeonCamera')
    cam.set_editor_property('tags', ['HCZSDungeonCamera'])
    cc = cam.get_component_by_class(u.CameraComponent)
    aspect = 16 / 9
    cc.set_editor_property('field_of_view', math.degrees(2 * math.atan(math.tan(math.radians(15)) * aspect)))
    cc.set_editor_property('aspect_ratio', aspect)
    cc.set_editor_property('constrain_aspect_ratio', False)
    post = cc.get_editor_property('post_process_settings')
    for key, value in dict(override_auto_exposure_method=True, auto_exposure_method=u.AutoExposureMethod.AEM_MANUAL,
                           override_auto_exposure_apply_physical_camera_exposure=True,
                           auto_exposure_apply_physical_camera_exposure=False,
                           override_auto_exposure_bias=True, auto_exposure_bias=0.0).items():
        post.set_editor_property(key, value)
    cc.set_editor_property('post_process_settings', post)
    cam.set_editor_property('auto_activate_for_player', u.AutoReceiveInput.PLAYER0)
    # chess_xuzhang.scn Global/Lights dir_light (Type 3, RenderCondition 0).  NeoX radiance is
    # Intensity * Colour * NdotL; UE Lambert divides by pi, so lux = Intensity * pi.
    sun = source_dir_light()
    light = actors.spawn_actor_from_class(u.DirectionalLight, u.Vector(0, 0, 2000),
                                          u.MathLibrary.make_rot_from_x(u.Vector(-sun['direction'][0], sun['direction'][2], sun['direction'][1])))
    light.set_actor_label('HCZSChessSunLight')
    lc = light.get_component_by_class(u.DirectionalLightComponent)
    lc.set_mobility(u.ComponentMobility.MOVABLE)
    lc.set_editor_property('intensity', sun['intensity'] * math.pi)
    r, g, b = [int(round(c * 255)) for c in sun['colour'][:3]]
    lc.set_editor_property('light_color', u.Color(r=r, g=g, b=b, a=255))
    lc.set_editor_property('use_temperature', False)
    lc.set_editor_property('dynamic_shadow_distance_movable_light', 20000.0)
    results['sunLight'] = sun
    results['actors'] = sorted('%s|%s' % (a.get_actor_label(), a.get_class().get_name()) for a in actors.get_all_level_actors()
                               if not a.get_actor_label().startswith('chess239_node_'))
    settings = world.get_world_settings()
    settings.set_editor_property('force_no_precomputed_lighting', True, u.PropertyAccessChangeNotifyMode.NEVER)
    mode = u.load_class(None, '/Script/Hczs.HczsDungeonMode')
    settings.set_editor_property('default_game_mode', mode if mode else u.GameModeBase)
    for asset in u.EditorAssetLibrary.list_assets(DEST, True, False):
        u.EditorAssetLibrary.save_asset(asset, only_if_is_dirty=False)
    check(u.EditorLoadingAndSavingUtils.save_map(world, MAP), 'Cannot save chess map')
    results.update(map=MAP, sceneGlbSha256=SCENE_SHA, lightmapBindingsSha256=digest(LIGHTMAPS),
                   piecesReportSha256=digest(PIECES), cellFxRecipeSha256=digest(CELL_FX), cells=CELLS, cellY=CELL_Y,
                   cameraSource=position, cameraRelative=CAMERA_RELATIVE, cameraFocusCell=start, playerRotY=face_y, verticalFov=30, fxSprites=spawned,
                   gameMode=mode.get_path_name() if mode else None,
                   limitations=['Baked UE4_lm term plus source dir_light (lux = Intensity * pi) on UE Lambert; the NeoX scene shader, fog, bloom/HDR and FullSfx vignette are not reproduced',
                                'Cell ring model effects (qipanzhuangtai) and ResUpper rise animation/Sfx are not rendered',
                                'Emblem height uses ResUpper_Pos + ResUpper_Vec; placement semantic unverified',
                                'Elsa reuses the battle mesh/idle_1 and battle scale; the original map avatar model is not confirmed'])
    return cam


def tick(delta):
    global task, stage
    if stage < 0:
        return
    u.log('Chess239 tick stage %d' % stage)
    try:
        if time.monotonic() - started > 120:
            raise RuntimeError('Chess screenshot deadline exceeded')
        if stage == 2 and time.monotonic() - started > 8:
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 720, str(OUT / 'chess239-ue.png'), camera=camera, delay=1)
            stage = 3
        elif stage == 3 and task.is_task_done():
            image = OUT / 'chess239-ue.png'
            check(image.is_file() and image.stat().st_size > 10000, 'Chess screenshot missing')
            results['screenshot'] = str(image)
            results['screenshotSha256'] = digest(image)
            (OUT / 'build-result.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), 'utf8')
            stage = -1
            u.unregister_slate_post_tick_callback(handle)
            u.SystemLibrary.quit_editor()
    except Exception:
        stage = -1
        u.log_error('Chess239 build failed: ' + traceback.format_exc())
        (OUT / 'build-error.txt').write_text(traceback.format_exc(), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


OUT.mkdir(parents=True, exist_ok=True)
for name in ('build-error.txt', 'build-result.json'):
    if (OUT / name).exists():
        (OUT / name).unlink()
try:
    camera = build()
    started = time.monotonic()
    stage = 2
    u.log('Chess239 map saved; waiting for screenshot')
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    u.log_error('Chess239 build failed: ' + traceback.format_exc())
    (OUT / 'build-error.txt').write_text(traceback.format_exc(), 'utf8')
    u.SystemLibrary.quit_editor()
