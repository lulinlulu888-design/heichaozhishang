"""Import pinned source environments into independent UE maps and render them.

Run once in the full editor via -ExecCmds="py <this file>". This restores
environment geometry/colour, not encounter selection, actors or game rules.
Existing maps are loaded for rendering; incomplete imports are never overwritten.
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

BASE = ROOT / 'analysis/battle-visual/prologue-theatre'
OUT = ROOT / 'analysis/unreal/battle-reference'
SPECS = [('boss_theatre', 'Theatre', '0a5f5bb156634c8a5b1310cef0374322dee3e8929622054274c4cbc44382e832'),
         ('pszdu_battle_1', 'RuinedCity', '56ce6a0565ae113a709c6ab882f93eb91a6e9a6a7ef12b9bd5486f30c93f3828')]
surface_only = '-HczsStageSurfaceOnly' in u.SystemLibrary.get_command_line()
if surface_only:
    SPECS = [('boss_theatre_surface', 'TheatreSurface', 'ed4f4394fd63a4e647c29bd203b727565471cba55621a8d7752b0c29040a1a02')]
results = []
task = None
index = 0
started = time.monotonic()
camera = None
busy = False


def prepare(spec):
    name, label, expected = spec
    source = BASE / name / 'scene.glb'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError('Source GLB changed: ' + name)
    report = json.loads((BASE / name / 'export.json').read_text('utf8'))
    if report['sha256'] != expected:
        raise RuntimeError('Source report disagrees with pinned input')
    map_path = '/Game/Recovered/SourceStages/Maps/L_' + label
    destination = '/Game/Recovered/SourceStages/' + label
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    if u.EditorAssetLibrary.does_asset_exist(map_path):
        world = u.EditorLoadingAndSavingUtils.load_map(map_path)
        if not world:
            raise RuntimeError('Cannot load existing source stage')
    else:
        if u.EditorAssetLibrary.list_assets(destination, True, False):
            raise RuntimeError('Partial import retained at ' + destination)
        world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
        document, binary = split_glb(raw)
        for number, node in enumerate(document['nodes']):
            node['name'] = name + '_node_' + str(number)
        staged = OUT / (name + '-import.glb')
        staged.write_bytes(pack_glb(document, binary))
        pipeline, overrides = make_pipeline(u, {'import_operation': 'scene'})
        parameters = u.ImportAssetParameters()
        parameters.set_editor_property('is_automated', True)
        parameters.set_editor_property('replace_existing', False)
        parameters.set_editor_property('override_pipelines', overrides)
        parameters.set_editor_property('import_level', u.EditorLevelUtils.get_levels(world)[0])
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        if not manager.import_scene(destination, u.InterchangeManager.create_source_data(str(staged)), parameters):
            raise RuntimeError('Scene import failed: ' + name)
        spatial = list(actors.get_all_level_actors())
        adapter = actors.spawn_actor_from_class(u.Actor, u.Vector())
        adapter.set_actor_label('HCZSSourceStageAxisAdapter')
        adapter.get_editor_property('root_component').set_mobility(u.ComponentMobility.STATIC)
        for actor in spatial:
            if actor.get_editor_property('root_component') and actor.get_attach_parent_actor() is None:
                actor.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_WORLD, u.AttachmentRule.KEEP_WORLD,
                                      u.AttachmentRule.KEEP_WORLD, False)
        adapter.set_actor_scale3d(u.Vector(-1, 1, 1))
        source_camera = report['scope']['sourceCameras'][0]
        matrix = [float(v) for v in source_camera['Transform'].split(',')]
        # Existing verified glTF/UE adapter: (-source.x, source.z, source.y)*100.
        # FOV convention remains an explicit inspection assumption, not parity.
        location = u.Vector(-matrix[12] * 100, matrix[14] * 100, matrix[13] * 100)
        inspection = actors.spawn_actor_from_class(u.CameraActor, location, u.Rotator(pitch=0, yaw=-90, roll=0))
        inspection.set_actor_label('HCZSSourceStageCamera')
        component = inspection.get_component_by_class(u.CameraComponent)
        component.set_editor_property('field_of_view', float(source_camera['Fov']))
        component.set_editor_property('aspect_ratio', 20 / 9)
        component.set_editor_property('constrain_aspect_ratio', True)
        inspection.set_editor_property('auto_activate_for_player', u.AutoReceiveInput.PLAYER0)
        settings = world.get_world_settings()
        settings.set_editor_property('force_no_precomputed_lighting', True)
        settings.set_editor_property('default_game_mode', u.GameModeBase)
        for asset in u.EditorAssetLibrary.list_assets(destination, True, False):
            if not u.EditorAssetLibrary.save_asset(asset, only_if_is_dirty=False):
                raise RuntimeError('Cannot save imported asset: ' + asset)
        if not u.EditorLoadingAndSavingUtils.save_map(world, map_path):
            raise RuntimeError('Cannot save source stage map')
    cameras = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'HCZSSourceStageCamera']
    if len(cameras) != 1:
        raise RuntimeError('Source stage camera missing or duplicated')
    cameras[0].set_actor_rotation(u.Rotator(pitch=0, yaw=-90, roll=0), False)
    if name.endswith('_surface'):
        # Raw source direction/intensity/colour, expressed in UE's light units.
        # This is a direct-light adapter; no photometric parity is asserted.
        source_xml = ET.fromstring((ROOT / 'analysis/battle-visual/lightmaps/boss_theatre/scene.scn').read_bytes())
        light = next(e for e in source_xml.iter('light') if e.get('Name') == 'dir_light' and e.get('Enable') == 'true')
        existing = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'HCZSSourceTheatreDirectional']
        if len(existing) > 1:
            raise RuntimeError('Source directional light duplicated')
        xyz = [float(v) for v in light.get('Direction').split(',')]
        direction = u.Vector(-xyz[0], xyz[2], xyz[1])
        rotation = u.MathLibrary.find_look_at_rotation(u.Vector(), direction)
        sun = existing[0] if existing else actors.spawn_actor_from_class(u.DirectionalLight, u.Vector(), rotation)
        sun.set_actor_label('HCZSSourceTheatreDirectional')
        component = sun.get_component_by_class(u.DirectionalLightComponent)
        component.set_mobility(u.ComponentMobility.MOVABLE)
        component.set_intensity(float(light.get('Intensity')))
        rgba = [float(v) for v in light.find('Diffuse/Key_0').get('Color').split(',')]
        component.set_light_color(u.LinearColor(*rgba), False)
    camera_component = cameras[0].get_component_by_class(u.CameraComponent)
    source_fov = float(report['scope']['sourceCameras'][0]['Fov'])
    aspect = 20 / 9
    horizontal_fov = math.degrees(2 * math.atan(math.tan(math.radians(source_fov) / 2) * aspect))
    camera_component.set_editor_property('field_of_view', horizontal_fov)
    post = camera_component.get_editor_property('post_process_settings')
    for key, value in dict(override_auto_exposure_method=True,
        auto_exposure_method=u.AutoExposureMethod.AEM_MANUAL,
        override_auto_exposure_apply_physical_camera_exposure=True,
        auto_exposure_apply_physical_camera_exposure=False,
        override_auto_exposure_bias=True, auto_exposure_bias=0.0).items():
        post.set_editor_property(key, value)
    camera_component.set_editor_property('post_process_settings', post)
    camera_component.set_editor_property('post_process_blend_weight', 1.0)
    if not u.EditorLoadingAndSavingUtils.save_map(world, map_path):
        raise RuntimeError('Cannot save verified inspection camera')
    results.append(dict(source=name, map=map_path, sourceGlbSha256=expected,
        sourceMeshes=report['meshes'], sourceInstances=report['instances'], sourceTextures=report['textures'],
        screenshot=str(OUT / (name + '-ue.png')), originalCameraProjectionVerified=False,
        inspectionCamera=dict(sourceFov=source_fov, assumedVerticalFov=True,
            horizontalFov=horizontal_fov, aspectRatio=aspect, manualExposureBias=0),
        originalLightingRestored=False, encounterIntegrated=False))
    return cameras[0]


def tick(delta):
    global task, index, camera, started, busy
    # Interchange and map loading pump Slate while they block. Nested ticks
    # must not start another import or close the editor during the first one.
    if busy:
        return
    busy = True
    try:
        if time.monotonic() - started > 120:
            raise RuntimeError('Stage screenshot deadline exceeded')
        if camera is None:
            camera = prepare(SPECS[index])
            started = time.monotonic()
        elif task is None and time.monotonic() - started > 7:
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 720,
                results[-1]['screenshot'], camera=camera, delay=1)
        elif task is not None and task.is_task_done():
            image = Path(results[-1]['screenshot'])
            if not image.is_file() or image.stat().st_size < 10000:
                raise RuntimeError('Source stage screenshot missing')
            results[-1]['screenshotSha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
            index += 1
            if index < len(SPECS):
                task = camera = None
                started = time.monotonic()
            else:
                filename = 'source-stage-surface-import.json' if surface_only else 'source-stage-import.json'
                (OUT / filename).write_text(json.dumps(results, indent=2), 'utf8')
                u.unregister_slate_post_tick_callback(handle)
                u.SystemLibrary.quit_editor()
    except Exception:
        (OUT / 'stage-import-error.txt').write_text(traceback.format_exc(), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()
    finally:
        busy = False


OUT.mkdir(parents=True, exist_ok=True)
previous_error = OUT / 'stage-import-error.txt'
if previous_error.exists():
    previous_error.rename(OUT / ('stage-import-error-' + str(time.time_ns()) + '.txt'))
handle = u.register_slate_post_tick_callback(tick)
