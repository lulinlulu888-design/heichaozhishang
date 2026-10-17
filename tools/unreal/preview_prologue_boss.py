"""Import boss 2013 and play its source idle clip inside the recovered theatre.

Run with -ExecCmds="py <this file>". The reviewed L_Theatre map is not saved.
"""
import hashlib
import json
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import make_pipeline

REPORT = ROOT / 'analysis/prologue-boss/glb/export-report.json'
SCENE = ROOT / 'analysis/prologue-boss/resource-audit/source/scene/boss_theatre/boss_theatre.scn'
SCENE_SHA = 'a403f116cb65da739457a8ddf32c8ae65820c7428cfdec51735e41baa1c05921'
FUTURE = ROOT / 'analysis/characters/hero-003/battle/export/export-report.json'
FUTURE_SHA = '47fb3c0b3c9cf20cd1ad86d9a8948c62a3300037a29c52ad9586ccd3a33b2b07'
OUT = ROOT / 'analysis/prologue-boss/glb'
MAP = '/Game/Recovered/SourceStages/Maps/L_Theatre'
results = {}
camera = None
task = None
stage = -1
started = 0
handle = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def import_boss():
    report = json.loads(REPORT.read_text('utf8'))
    glb = Path(report['animatedGlb'])
    check(glb.is_file() and sha(glb) == report['animatedSha256'], 'Boss GLB identity changed')
    check(report['monsterId'] == 2013 and len(report['clipDurations']) == 7, 'Boss clip set changed')
    destination = '/Game/Recovered/Boss/Muou2013/v_' + report['animatedSha256'][:16]
    paths = u.EditorAssetLibrary.list_assets(destination, True, False)
    if not paths:
        pipeline, overrides = make_pipeline(u, dict(import_operation='asset'))
        common = pipeline.get_editor_property('common_skeletal_meshes_and_animations_properties')
        common.set_editor_property('try_auto_select_skeleton', False)
        params = u.ImportAssetParameters()
        for key, value in dict(is_automated=True, replace_existing=False, override_pipelines=overrides).items():
            params.set_editor_property(key, value)
        returned = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
            destination, u.InterchangeManager.create_source_data(str(glb)), params)
        check(returned[0] if isinstance(returned, tuple) else returned, 'Interchange rejected boss 2013')
        paths = u.EditorAssetLibrary.list_assets(destination, True, False)
        for path in paths:
            asset = u.load_asset(path)
            u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsBossSourceGLB', report['animatedSha256'])
            check(u.EditorAssetLibrary.save_loaded_asset(asset, False), 'Boss asset save failed')
    objects = [u.load_asset(path) for path in paths]
    check(objects and all(u.EditorAssetLibrary.get_metadata_tag(asset, 'HczsBossSourceGLB') == report['animatedSha256'] for asset in objects),
          'Boss import namespace does not match this GLB')
    meshes = [asset for asset in objects if isinstance(asset, u.SkeletalMesh)]
    sequences = [asset for asset in objects if isinstance(asset, u.AnimSequence)]
    check(len(meshes) == 1 and len(sequences) == 7, 'Expected one boss mesh and seven clips')
    idle = next((item for item in sequences if 'idle' in item.get_name().lower()), None)
    check(idle is not None, 'Source idle clip was not imported')
    return meshes[0], idle, report


def import_future():
    report = json.loads(FUTURE.read_text('utf8'))
    glb = Path(report['output'])
    check(glb.is_file() and sha(glb) == FUTURE_SHA and report.get('selection', {}).get('characterId') == 3, 'Future battle GLB identity changed')
    check(report['selection']['purpose'] == 'battle' and report['selection']['clip'] == 'idle_1', 'Future export is not the battle idle')
    destination = '/Game/Recovered/Battle/Future/v_' + FUTURE_SHA[:16]
    paths = u.EditorAssetLibrary.list_assets(destination, True, False)
    if not paths:
        pipeline, overrides = make_pipeline(u, dict(import_operation='asset'))
        common = pipeline.get_editor_property('common_skeletal_meshes_and_animations_properties')
        common.set_editor_property('try_auto_select_skeleton', False)
        params = u.ImportAssetParameters()
        for key, value in dict(is_automated=True, replace_existing=False, override_pipelines=overrides).items():
            params.set_editor_property(key, value)
        returned = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
            destination, u.InterchangeManager.create_source_data(str(glb)), params)
        check(returned[0] if isinstance(returned, tuple) else returned, 'Interchange rejected Future')
        paths = u.EditorAssetLibrary.list_assets(destination, True, False)
        for path in paths:
            asset = u.load_asset(path)
            u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsFutureSourceGLB', FUTURE_SHA)
            check(u.EditorAssetLibrary.save_loaded_asset(asset, False), 'Future asset save failed')
    objects = [u.load_asset(path) for path in paths]
    meshes = [asset for asset in objects if isinstance(asset, u.SkeletalMesh)]
    sequences = [asset for asset in objects if isinstance(asset, u.AnimSequence)]
    check(len(meshes) == 1 and len(sequences) == 1, 'Expected one Future mesh and idle')
    return meshes[0], sequences[0]


def source_placement():
    raw = SCENE.read_bytes()
    check(sha(SCENE) == SCENE_SHA, 'Theatre scene bytes changed')
    root = ET.fromstring(raw)
    files = {node.tag.split('_', 1)[1]: node.get('Path') for node in root.iter() if node.tag.startswith('File_') and node.get('Path')}
    model = next(node for node in root.iter('model') if node.get('Name') == 'muoumaxituan_1743')
    elsa = next(node for node in root.iter('model')
                if node.get('Name') == '1_2' and files.get(node.get('FilePathIndex'), '').endswith('ailisha.gim'))
    future = next(node for node in root.iter('model')
                  if node.get('Name') == '3_4' and files.get(node.get('FilePathIndex'), '').endswith('future.gim'))
    camera_node = next(node for node in root.iter('Camera') if node.get('Name') == 'camera_1')
    position = [float(v) for v in model.get('Position').split(',')]
    rotation = [float(v) for v in model.get('Rotation').split(',')]
    camera = [float(v) for v in camera_node.get('Transform').split(',')]
    check(len(position) == 3 and len(rotation) == 16 and len(camera) == 16, 'Theatre transform width changed')
    check(abs(float(camera_node.get('Fov')) - 45) < 1e-3, 'Theatre camera_1 FOV changed')
    elsa_position = [float(v) for v in elsa.get('Position').split(',')]
    elsa_rotation = [float(v) for v in elsa.get('Rotation').split(',')]
    future_position = [float(v) for v in future.get('Position').split(',')]
    future_rotation = [float(v) for v in future.get('Rotation').split(',')]
    return position, rotation, camera, elsa_position, elsa_rotation, future_position, future_rotation


def to_ue(values):
    return u.Vector(-values[0], values[2], values[1])


def build():
    mesh, idle, report = import_boss()
    position, rotation, camera_matrix, elsa_position, elsa_rotation, future_position, future_rotation = source_placement()
    future_mesh, future_idle = import_future()
    check(u.EditorAssetLibrary.does_asset_exist(MAP), 'Recovered theatre map is missing')
    check(u.EditorLoadingAndSavingUtils.load_map(MAP), 'Cannot open L_Theatre')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    # Same centimetre mapping as the chess map: source (x, y, z) -> UE (-x, z, y) * 100.
    location = to_ue(position) * 100
    actor = actors.spawn_actor_from_class(u.SkeletalMeshActor, location, u.MathLibrary.make_rot_from_xz(to_ue(rotation[8:11]), to_ue(rotation[4:7])))
    actor.set_actor_label('HCZSBoss2013')
    actor.set_editor_property('tags', ['HCZSBoss2013'])
    component = actor.get_component_by_class(u.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    component.override_animation_data(idle, True, True, 0, 1)
    component.play_animation(idle, True)
    component.set_update_animation_in_editor(True)
    component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    elsa_mesh = u.load_asset('/Game/Recovered/Battle/Elsa/elsa_battle.elsa_battle')
    elsa_idle = u.load_asset('/Game/Recovered/Battle/Elsa/elsa_battleidle_1.elsa_battleidle_1')
    check(isinstance(elsa_mesh, u.SkeletalMesh) and isinstance(elsa_idle, u.AnimSequence), 'Recovered Elsa battle idle is missing')
    elsa_actor = actors.spawn_actor_from_class(
        u.SkeletalMeshActor, to_ue(elsa_position) * 100,
        u.MathLibrary.make_rot_from_xz(to_ue(elsa_rotation[8:11]), to_ue(elsa_rotation[4:7])))
    elsa_actor.set_actor_label('HCZSTheatreElsa')
    elsa_component = elsa_actor.get_component_by_class(u.SkeletalMeshComponent)
    elsa_component.set_skeletal_mesh_asset(elsa_mesh)
    elsa_component.override_animation_data(elsa_idle, True, True, 0, 1)
    elsa_component.play_animation(elsa_idle, True)
    elsa_component.set_update_animation_in_editor(True)
    elsa_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    future_actor = actors.spawn_actor_from_class(
        u.SkeletalMeshActor, to_ue(future_position) * 100,
        u.MathLibrary.make_rot_from_xz(to_ue(future_rotation[8:11]), to_ue(future_rotation[4:7])))
    future_actor.set_actor_label('HCZSTheatreFuture')
    future_component = future_actor.get_component_by_class(u.SkeletalMeshComponent)
    future_component.set_skeletal_mesh_asset(future_mesh)
    future_component.override_animation_data(future_idle, True, True, 0, 1)
    future_component.play_animation(future_idle, True)
    future_component.set_update_animation_in_editor(True)
    future_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    origin, extent = actor.get_actor_bounds(False)
    future_origin, future_extent = future_actor.get_actor_bounds(False)
    cam = actors.spawn_actor_from_class(
        u.CameraActor, to_ue(camera_matrix[12:15]) * 100,
        u.MathLibrary.make_rot_from_xz(to_ue(camera_matrix[8:11]), to_ue(camera_matrix[4:7])))
    cam.set_actor_label('HCZSBossPreviewCamera')
    cam.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 45)
    results.update(mesh=mesh.get_path_name(), idle=idle.get_name(), playLength=idle.get_play_length(),
                   clips=7, sourcePosition=position, bounds=[origin.x, origin.y, origin.z, extent.x, extent.y, extent.z],
                   scale=[actor.get_actor_scale3d().x, actor.get_actor_scale3d().y, actor.get_actor_scale3d().z],
                   elsaPosition=elsa_position, elsaIdle=elsa_idle.get_name(),
                   futurePosition=future_position, futureIdle=future_idle.get_name(),
                   futureBounds=[future_origin.x, future_origin.y, future_origin.z, future_extent.x, future_extent.y, future_extent.z],
                   futureMesh=future_mesh.get_path_name(), futureSha256=FUTURE_SHA,
                   sourceSha256=report['animatedSha256'], sceneSha256=SCENE_SHA, camera='camera_1', cameraFov=45,
                   mapSaved=False,
                   limitations=['Placement uses the source model position and camera_1. Material, SFX and battle rules are not ported.',
                                'Transform phase and battle 1703 rules are not part of this preview.'])
    look_from = future_origin + u.Vector(0, 700, 180)
    close = actors.spawn_actor_from_class(u.CameraActor, look_from, u.MathLibrary.find_look_at_rotation(look_from, future_origin))
    close.set_actor_label('HCZSFutureBoundsCamera')
    close.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 45)
    results['futureBoundsCamera'] = 'placement-check'
    return cam, close


def tick(delta):
    global task, stage
    if stage < 0:
        return
    try:
        if time.monotonic() - started > 180:
            raise RuntimeError('Boss preview deadline exceeded')
        if stage == 2 and time.monotonic() - started > 6:
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 900, str(OUT / 'boss-2013-ue.png'), camera=camera, delay=1)
            stage = 3
        elif stage == 3 and task.is_task_done():
            image = OUT / 'boss-2013-ue.png'
            check(image.is_file() and image.stat().st_size > 10000, 'Boss screenshot missing')
            results['screenshot'] = str(image)
            results['screenshotSha256'] = sha(image)
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 900, str(OUT / 'future-bounds-ue.png'), camera=close_camera, delay=1)
            stage = 4
        elif stage == 4 and task.is_task_done():
            close_image = OUT / 'future-bounds-ue.png'
            check(close_image.is_file() and close_image.stat().st_size > 10000, 'Future bounds screenshot missing')
            results['futureBoundsScreenshot'] = str(close_image)
            results['futureBoundsScreenshotSha256'] = sha(close_image)
            (OUT / 'ue-preview.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), 'utf8')
            stage = -1
            u.unregister_slate_post_tick_callback(handle)
            u.SystemLibrary.quit_editor()
    except Exception:
        stage = -1
        (OUT / 'ue-preview-error.txt').write_text(traceback.format_exc(), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


for name in ('ue-preview-error.txt', 'ue-preview.json'):
    path = OUT / name
    if path.exists():
        path.unlink()
try:
    camera, close_camera = build()
    started = time.monotonic()
    stage = 2
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    (OUT / 'ue-preview-error.txt').write_text(traceback.format_exc(), 'utf8')
    u.SystemLibrary.quit_editor()
