"""Import every passed hero idle GLB and photograph them on the theatre party line.

Run with -ExecCmds="py <this file>"; add -HczsLineupPurpose=hall for the hall idles (default battle).
Inputs come from analysis/characters/batch-<purpose>.json; each import lives in
/Game/Recovered/Heroes/HeroNNN/{Battle|HallIdle}/v_<sha16>. L_Theatre is not saved and is only a neutral
inspection stage for hall idles. Scope: native import, idle playback and framing only.
"""
import hashlib
import json
import math
import sys
import time
import traceback
from pathlib import Path

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import make_pipeline, read_glb
from verify_battle_scene import pose_readback
import xml.etree.ElementTree as ET

MAP = '/Game/Recovered/SourceStages/Maps/L_Theatre'
SCENE = ROOT / 'analysis/prologue-boss/resource-audit/source/scene/boss_theatre/boss_theatre.scn'
SCENE_SHA = 'a403f116cb65da739457a8ddf32c8ae65820c7428cfdec51735e41baa1c05921'
_purpose = [a.split('=', 1)[1] for a in u.SystemLibrary.get_command_line().split() if a.startswith('-HczsLineupPurpose=')]
PURPOSE = _purpose[0] if _purpose else 'battle'
if PURPOSE not in ('battle', 'hall'):
    raise RuntimeError('Unsupported lineup purpose ' + PURPOSE)
BATCH = ROOT / 'analysis/characters' / ('batch-' + PURPOSE + '.json')
OUT = ROOT / 'analysis/characters' / (PURPOSE + '-lineup')
PAGE = 6
TAG = 'HczsHeroBattleGLB'
results = dict(heroes=[], pages=[], mapSaved=False)
pages = []
page_index = 0
task = None
started = 0
handle = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def to_ue(values):
    return u.Vector(-values[0], values[2], values[1])


def theatre_line():
    check(sha(SCENE) == SCENE_SHA, 'Theatre scene bytes changed')
    root = ET.fromstring(SCENE.read_bytes())
    files = {n.tag.split('_', 1)[1]: n.get('Path') for n in root.iter() if n.tag.startswith('File_') and n.get('Path')}
    future = next(n for n in root.iter('model')
                  if n.get('Name') == '3_4' and files.get(n.get('FilePathIndex'), '').endswith('future.gim'))
    camera = [float(v) for v in next(n for n in root.iter('Camera') if n.get('Name') == 'camera_1').get('Transform').split(',')]
    return ([float(v) for v in future.get('Position').split(',')],
            [float(v) for v in future.get('Rotation').split(',')], camera)


def import_hero(row):
    report_path = ROOT / 'analysis/characters' / ('hero-' + str(row['characterId']).zfill(3)) / PURPOSE / 'export/export-report.json'
    report = json.loads(report_path.read_text('utf8'))
    glb = Path(report['output'])
    check(glb.is_file() and sha(glb) == row['sha256'] == report['sha256'], 'Hero GLB identity changed: ' + str(row['characterId']))
    check(report['selection']['purpose'] == PURPOSE and report['selection']['characterId'] == row['characterId'], 'Not a ' + PURPOSE + ' export')
    # Hall/ already holds untagged single-hero preview imports (Hero003), so hall lineups use HallIdle/.
    destination = ('/Game/Recovered/Heroes/Hero' + str(row['characterId']).zfill(3) + '/'
                   + ('Battle' if PURPOSE == 'battle' else 'HallIdle') + '/v_' + row['sha256'][:16])
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
        check(returned[0] if isinstance(returned, tuple) else returned, 'Interchange rejected hero ' + str(row['characterId']))
        paths = u.EditorAssetLibrary.list_assets(destination, True, False)
        for path in paths:
            asset = u.load_asset(path)
            u.EditorAssetLibrary.set_metadata_tag(asset, TAG, row['sha256'])
            check(u.EditorAssetLibrary.save_loaded_asset(asset, False), 'Hero asset save failed')
    objects = [u.load_asset(path) for path in paths]
    tags = [u.EditorAssetLibrary.get_metadata_tag(a, TAG) for a in objects]
    if row['sha256'] in tags and all(t in ('', row['sha256']) for t in tags):
        # Interchange can register late assets after the first tagging pass; this hash-named namespace is ours.
        for asset, tag in zip(objects, tags):
            if not tag:
                u.EditorAssetLibrary.set_metadata_tag(asset, TAG, row['sha256'])
                check(u.EditorAssetLibrary.save_loaded_asset(asset, False), 'Hero asset save failed')
    check(objects and all(u.EditorAssetLibrary.get_metadata_tag(a, TAG) == row['sha256'] for a in objects),
          'Unowned or partial hero import namespace %s: %s' % (destination, sorted(
              {a.get_name() + '=' + (u.EditorAssetLibrary.get_metadata_tag(a, TAG) or '-')[:8] for a in objects})[:8]))
    meshes = [a for a in objects if isinstance(a, u.SkeletalMesh)]
    sequences = [a for a in objects if isinstance(a, u.AnimSequence)]
    check(len(meshes) == 1 and len(sequences) == 1, 'Expected one mesh and one idle for hero ' + str(row['characterId']))
    expected = report['animations'][0]['duration_source_seconds']
    check(meshes[0].get_editor_property('skeleton') == sequences[0].get_editor_property('skeleton'), 'Skeleton mismatch')
    check(abs(sequences[0].get_play_length() - expected) <= 0.001, 'Imported idle duration differs')
    return meshes[0], sequences[0], report, glb


def build():
    check(u.EditorLoadingAndSavingUtils.load_map(MAP), 'Cannot open L_Theatre')
    future_position, future_rotation, camera_matrix = theatre_line()
    rotation = u.MathLibrary.make_rot_from_xz(to_ue(future_rotation[8:11]), to_ue(future_rotation[4:7]))
    line = to_ue(future_position) * 100
    camera_side = 1 if to_ue(camera_matrix[12:15]).y * 100 > line.y else -1
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    rows = [r for r in json.loads(BATCH.read_text('utf8'))['results'] if r['passed']]
    spawned = []
    for row in rows:
        mesh, idle, report, glb = import_hero(row)
        actor = actors.spawn_actor_from_class(u.SkeletalMeshActor, line, rotation)
        actor.set_actor_label('HCZSHeroLineup' + str(row['characterId']).zfill(3))
        component = actor.get_component_by_class(u.SkeletalMeshComponent)
        component.set_skeletal_mesh_asset(mesh)
        component.override_animation_data(idle, True, True, 0, 1)
        component.play_animation(idle, True)
        component.set_update_animation_in_editor(True)
        component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        origin, extent = actor.get_actor_bounds(False)
        entry = dict(characterId=row['characterId'], name=row['name'], sha256=row['sha256'], mesh=mesh.get_path_name(),
                     idle=idle.get_name(), playLength=idle.get_play_length(), bones=component.get_num_bones(),
                     materials=component.get_num_materials(), boundsExtent=[extent.x, extent.y, extent.z],
                     referenceSkin='reference_pose_mismatch' in report['reference_skin'],
                     jointLocalSource=report.get('joint_local_source'),
                     noShaderSlots=report.get('unresolved_no_shader_slots', []),
                     libraryOnlyBones=len(report['selection'].get('libraryOnlyBones', [])))
        entry['nativePose'] = {k: v for k, v in pose_readback(u, mesh, idle, read_glb(glb.read_bytes())).items() if k != 'samples'}
        check(entry['nativePose']['sampled_pose_changes'], 'Native idle pose does not move for hero ' + str(row['characterId']))
        results['heroes'].append(entry)
        spawned.append((actor, origin - actor.get_actor_location(), extent))
    width = 2.4 * max(max(e.x, e.y) for _, _, e in spawned)
    height = 2 * max(e.z for _, _, e in spawned)
    for start in range(0, len(spawned), PAGE):
        group = spawned[start:start + PAGE]
        for slot, (actor, _, _) in enumerate(group):
            actor.set_actor_location(line + u.Vector((slot - (len(group) - 1) / 2) * width, 0, 0), False, False)
        span = PAGE * width
        distance = max(span / 2 / math.tan(math.radians(22.5)), height / 2 / math.tan(math.radians(22.5 * 9 / 16))) * 1.08
        center = line + u.Vector(0, 0, spawned[0][1].z)
        eye = center + u.Vector(0, camera_side * distance, 0)
        cam = actors.spawn_actor_from_class(u.CameraActor, eye, u.MathLibrary.find_look_at_rotation(eye, center))
        cam.set_actor_label('HCZSHeroLineupCamera' + str(start // PAGE))
        cam.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 45)
        pages.append(dict(camera=cam, actors=[a for a, _, _ in group],
                          ids=[results['heroes'][start + i]['characterId'] for i in range(len(group))]))
    boss_side = 1 if to_ue(theatre_boss()).x * 100 > line.x else -1
    vertical = math.atan(math.tan(math.radians(22.5)) * 9 / 16)
    for entry, (actor, offset, extent) in zip(results['heroes'], spawned):
        origin = line + offset
        eye = origin + u.Vector(boss_side * extent.z * 1.15 / math.tan(vertical), 0, 0)
        cam = actors.spawn_actor_from_class(u.CameraActor, eye, u.MathLibrary.find_look_at_rotation(eye, origin))
        cam.set_actor_label('HCZSHeroFrontCamera' + str(entry['characterId']).zfill(3))
        cam.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 45)
        pages.append(dict(camera=cam, actors=[actor], ids=[entry['characterId']], front=True, location=line))
    results.update(purpose=PURPOSE, page=PAGE, slotWidth=width, cameraSide=camera_side, frontSide=boss_side,
                   sourceLine='Future instance 3_4 position and rotation; front close-ups look from the boss side',
                   engineVersion=u.SystemLibrary.get_engine_version())


def theatre_boss():
    root = ET.fromstring(SCENE.read_bytes())
    boss = next(n for n in root.iter('model') if n.get('Name') == 'muoumaxituan_1743')
    return [float(v) for v in boss.get('Position').split(',')]


def show(page):
    for other in pages:
        for actor in other['actors']:
            actor.set_is_temporarily_hidden_in_editor(True)
    for actor in page['actors']:
        if 'location' in page:
            actor.set_actor_location(page['location'], False, False)
        actor.set_is_temporarily_hidden_in_editor(False)


def image_name(page):
    return ('front-' + str(page['ids'][0]).zfill(3) if page.get('front') else 'page-' + str(page_index)) + '.png'


def tick(delta):
    global task, page_index
    try:
        check(time.monotonic() - started < 900, 'Lineup deadline exceeded')
        if task is None:
            if time.monotonic() - started < 6:
                return
            show(pages[page_index])
            task = u.AutomationLibrary.take_high_res_screenshot(
                1600, 900, str(OUT / image_name(pages[page_index])), camera=pages[page_index]['camera'], delay=1)
        elif task.is_task_done():
            image = OUT / image_name(pages[page_index])
            check(image.is_file() and image.stat().st_size > 10000, 'Lineup screenshot missing')
            results['pages'].append(dict(ids=pages[page_index]['ids'], screenshot=str(image), sha256=sha(image)))
            page_index += 1
            task = None
            if page_index == len(pages):
                (OUT / 'lineup.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), 'utf8')
                u.unregister_slate_post_tick_callback(handle)
                u.SystemLibrary.quit_editor()
    except Exception:
        (OUT / 'lineup-error.txt').write_text(traceback.format_exc(), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


OUT.mkdir(parents=True, exist_ok=True)
for stale in ('lineup.json', 'lineup-error.txt'):
    if (OUT / stale).exists():
        (OUT / stale).unlink()
try:
    build()
    started = time.monotonic()
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    (OUT / 'lineup-error.txt').write_text(traceback.format_exc(), 'utf8')
    u.SystemLibrary.quit_editor()
