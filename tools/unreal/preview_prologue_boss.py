"""Import boss 2013 and play its source idle clip inside the recovered theatre.

Run with -ExecCmds="py <this file>". The reviewed L_Theatre map is not saved.
"""
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import make_pipeline

REPORT = ROOT / 'analysis/prologue-boss/glb/export-report.json'
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


def build():
    mesh, idle, report = import_boss()
    check(u.EditorAssetLibrary.does_asset_exist(MAP), 'Recovered theatre map is missing')
    check(u.EditorLoadingAndSavingUtils.load_map(MAP), 'Cannot open L_Theatre')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    actor = actors.spawn_actor_from_class(u.SkeletalMeshActor, u.Vector(0, 0, 0))
    actor.set_actor_label('HCZSBoss2013')
    actor.set_editor_property('tags', ['HCZSBoss2013'])
    component = actor.get_component_by_class(u.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    component.override_animation_data(idle, True, True, 0, 1)
    component.play_animation(idle, True)
    component.set_update_animation_in_editor(True)
    component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    origin, extent = actor.get_actor_bounds(False)
    longest = max(extent.x, extent.y, extent.z)
    if longest < 50:
        actor.set_actor_scale3d(u.Vector(100, 100, 100))
        origin, extent = actor.get_actor_bounds(False)
        longest = max(extent.x, extent.y, extent.z)
    cam = actors.spawn_actor_from_class(u.CameraActor, origin + u.Vector(0, -longest * 4.5, longest * 0.35))
    cam.set_actor_label('HCZSBossPreviewCamera')
    cam.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 30)
    cam.set_actor_rotation(u.MathLibrary.find_look_at_rotation(cam.get_actor_location(), origin), False)
    results.update(mesh=mesh.get_path_name(), idle=idle.get_name(), playLength=idle.get_play_length(),
                   clips=7, bounds=[origin.x, origin.y, origin.z, extent.x, extent.y, extent.z],
                   scale=[actor.get_actor_scale3d().x, actor.get_actor_scale3d().y, actor.get_actor_scale3d().z],
                   sourceSha256=report['animatedSha256'], mapSaved=False,
                   limitations=['Source XYZ was imported without a reviewed theatre placement or NeoX material port.',
                                'Transform phase and battle 1703 rules are not part of this preview.'])
    return cam


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
    camera = build()
    started = time.monotonic()
    stage = 2
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    (OUT / 'ue-preview-error.txt').write_text(traceback.format_exc(), 'utf8')
    u.SystemLibrary.quit_editor()
