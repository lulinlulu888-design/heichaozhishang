"""Import a recovered hall-idle GLB and render a separate hall comparison.

Run full Editor in L_ElsaHallFxPreview with -HczsHeroId=3. Existing hall and
Elsa assets remain untouched. Reject unrelated/partial destination contents.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import traceback

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import make_pipeline

SOURCE_MAP = '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview'
match = re.search(r'(?:^|\s)-HczsHeroId=(\d+)(?:\s|$)', u.SystemLibrary.get_command_line())
HERO = int(match[1]) if match else 3
BASE = ROOT / 'analysis/characters' / ('hero-' + str(HERO).zfill(3)) / 'hall'
OUT = BASE / 'unreal-preview'
OUT.mkdir(parents=True, exist_ok=True)
task = None
frame = 0
busy = False
first_capture = None
first_capture_elapsed = None
simulation_world = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    report = json.loads((BASE / 'export/export-report.json').read_text('utf8'))
    glb = Path(report['output'])
    if not glb.resolve().is_relative_to(BASE.resolve()) or sha(glb) != report['sha256'] or report['selection']['characterId'] != HERO:
        raise RuntimeError('Source hero export differs')
    input_sha = report['sha256']
    expected_seconds = report['animations'][0]['duration_source_seconds']
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split('.')[0] != SOURCE_MAP:
        raise RuntimeError('Open the saved source hall before creating a comparison')
    source_file = ROOT / 'clients/unreal5 5.8/Content' / (SOURCE_MAP.removeprefix('/Game/') + '.umap')
    source_hash = sha(source_file)
    destination = '/Game/Recovered/Heroes/Hero' + str(HERO).zfill(3) + '/Hall/v_' + input_sha[:16]
    target_map = '/Game/Recovered/Hall/Maps/L_Hero' + str(HERO).zfill(3) + '_' + input_sha[:12] + '_SourceColor'
    if u.EditorAssetLibrary.does_asset_exist(target_map):
        raise RuntimeError('Existing hero comparison retained; inspect it instead of overwriting')
    paths = u.EditorAssetLibrary.list_assets(destination, True, False)
    if not paths:
        pipeline, overrides = make_pipeline(u, dict(import_operation='asset'))
        common = pipeline.get_editor_property('common_skeletal_meshes_and_animations_properties')
        common.set_editor_property('try_auto_select_skeleton', False)
        params = u.ImportAssetParameters()
        for key, value in dict(is_automated=True, replace_existing=False, override_pipelines=overrides).items():
            params.set_editor_property(key, value)
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        returned = manager.import_asset(destination, u.InterchangeManager.create_source_data(str(glb)), params)
        if not (returned[0] if isinstance(returned,tuple) else returned):
            raise RuntimeError('Interchange rejected source hero')
        paths = u.EditorAssetLibrary.list_assets(destination, True, False)
        for path in paths:
            asset = u.load_asset(path)
            u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsHeroSourceGLB', input_sha)
            if not u.EditorAssetLibrary.save_loaded_asset(asset, False):
                raise RuntimeError('Imported hero asset save failed')
    objects = [u.load_asset(p) for p in paths]
    if not objects or any(u.EditorAssetLibrary.get_metadata_tag(a,'HczsHeroSourceGLB') != input_sha for a in objects):
        raise RuntimeError('Unowned or partial hero import namespace')
    meshes = [a for a in objects if isinstance(a,u.SkeletalMesh)]
    sequences = [a for a in objects if isinstance(a,u.AnimSequence)]
    if len(meshes) != 1 or len(sequences) != 1:
        raise RuntimeError('Expected one mesh and one exact hall animation')
    mesh, animation = meshes[0], sequences[0]
    if mesh.get_editor_property('skeleton') != animation.get_editor_property('skeleton') or abs(animation.get_play_length()-expected_seconds) > 0.001:
        raise RuntimeError('Imported animation skeleton or duration differs')
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    characters = [a for a in actors if a.get_actor_label() == 'HCZS_elsa']
    cameras = [a for a in actors if a.get_actor_label() == 'HCZSInspectionCamera']
    if len(characters) != 1 or len(cameras) != 1:
        raise RuntimeError('Original hall actor/camera mapping is not unique')
    old_actor = characters[0]
    old_component = old_actor.get_component_by_class(u.SkeletalMeshComponent)
    original_mesh = old_component.get_editor_property('skeletal_mesh_asset').get_path_name()
    actor_tools = u.get_editor_subsystem(u.EditorActorSubsystem)
    actor = actor_tools.spawn_actor_from_class(u.SkeletalMeshActor, old_actor.get_actor_location(), old_actor.get_actor_rotation())
    component = actor.get_component_by_class(u.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    component.override_animation_data(animation, True, True, 0, 1)
    component.play_animation(animation, True)
    component.set_update_animation_in_editor(True)
    component.set_component_tick_enabled(True)
    from import_recovered_assets import read_glb
    from repair_battle_visual_materials import source_colour_material, duplicate_texture
    from verify_battle_scene import source_material_name
    document = read_glb(glb.read_bytes())
    color_sha = hashlib.sha256((input_sha + 'source-color-exposure-adapter-v1').encode()).hexdigest()
    color_plan = dict(destination='/Game/Recovered/Heroes/Hero'+str(HERO).zfill(3)+'/HallColor/v_'+color_sha[:16],recipe_sha256=color_sha)
    textures = {obj.get_name():obj for obj in objects if isinstance(obj,u.Texture2D)}
    original_materials = {source_material_name(m['name']):m for m in document['materials']}
    color_rows = []
    for slot in range(component.get_num_materials()):
        interface = component.get_material(slot)
        source_material = original_materials.get(interface.get_name())
        if source_material is None:
            raise RuntimeError('Native material slot cannot be mapped to source: '+interface.get_name())
        pbr = source_material['pbrMetallicRoughness']
        tex = document['textures'][pbr['baseColorTexture']['index']]
        image = document['images'][tex['source']]
        key = source_material_name(image['name'])
        if key not in textures:
            raise RuntimeError('Native color texture cannot be mapped to source: '+key)
        texture = duplicate_texture(u,color_plan,textures[key].get_path_name(),numeric=False)
        row = dict(side='hero'+str(HERO), component_slot=slot,
            blend=source_material.get('alphaMode','OPAQUE'),cutoff=source_material.get('alphaCutoff',0.5),
            tint=pbr.get('baseColorFactor',[1,1,1,1]),two_sided=source_material.get('doubleSided',False))
        material = source_colour_material(u,color_plan,row,texture)
        component.set_material(slot,material)
        color_rows.append(dict(slot=slot,sourceMaterial=source_material['name'],material=material.get_path_name(),texture=texture.get_path_name()))
    entity = report['selection']['sourceTables']['entity']['rows'][0]['fields']
    # New component avoids retaining the old mesh's evaluated bone array. Bake
    # only the existing hall coordinate reflection into this independent actor.
    previous_scale = old_actor.get_actor_scale3d()
    source_scale = entity['SCALE_IN_HALL']
    actor.set_actor_scale3d(u.Vector(*[(-1 if old < 0 else 1)*value for old,value in
        zip((previous_scale.x,previous_scale.y,previous_scale.z), source_scale)]))
    actor.set_actor_label('HCZS_Hero' + str(HERO).zfill(3))
    if not actor_tools.destroy_actor(old_actor):
        raise RuntimeError('Cannot remove old actor from independent comparison world')
    if not u.EditorLoadingAndSavingUtils.save_map(world, target_map) or sha(source_file) != source_hash:
        raise RuntimeError('Comparison map save or original map hash check failed')
    outcome = dict(characterId=HERO, name=report['selection']['name'], map=target_map,
        sourceGlbSha256=report['sha256'], importedGlbSha256=input_sha, sourceMap=SOURCE_MAP, sourceMapSha256=source_hash,
        sourceMapUnchanged=True, mesh=mesh.get_path_name(), animation=animation.get_path_name(),
        replacedComparisonMesh=original_mesh, seconds=animation.get_play_length(),
        boneCount=component.get_num_bones(), materials=component.get_num_materials(),
        sourceScale=entity['SCALE_IN_HALL'], nativeRenderVerified=False,
        colorMaterials=color_rows, colorScope='Source color with UE exposure compensation; not original NeoX shaders',
        scope='Independent color-reference hall comparison; NeoX shading, physics, UI hero selection and gameplay unverified.')
    from verify_battle_scene import pose_readback
    outcome['nativePoseReadback'] = pose_readback(u, mesh, animation, read_glb(glb.read_bytes()))
    p = actor.get_actor_location()
    outcome['actorLocation'] = [p.x,p.y,p.z]
    outcome['actorWorldScale'] = [actor.get_actor_scale3d().x,actor.get_actor_scale3d().y,actor.get_actor_scale3d().z]
    (OUT / 'import-readback.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),'utf8')
    return cameras[0], component, outcome


def capture_bones():
    rows = []
    for i in range(component.get_num_bones()):
        name = component.get_bone_name(i)
        p = component.get_socket_location(name)
        rows.append(dict(name=str(name), position=[p.x,p.y,p.z]))
    return rows


def tick(delta):
    global task, frame, busy, first_capture, first_capture_elapsed, simulation_world, component, camera
    if busy:
        return
    busy = True
    try:
        elapsed = time.monotonic() - started
        if elapsed > 120:
            raise RuntimeError('Hero render deadline exceeded')
        if simulation_world is None:
            simulation_world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
            if not simulation_world:
                return
            heroes = [a for a in u.GameplayStatics.get_all_actors_of_class(simulation_world,u.SkeletalMeshActor)
                if a.get_actor_label() == 'HCZS_Hero'+str(HERO).zfill(3)]
            cameras = [a for a in u.GameplayStatics.get_all_actors_of_class(simulation_world,u.CameraActor)
                if a.get_actor_label() == 'HCZSInspectionCamera']
            if len(heroes) != 1 or len(cameras) != 1:
                raise RuntimeError('PIE actor/camera mapping differs')
            component = heroes[0].get_component_by_class(u.SkeletalMeshComponent)
            camera = cameras[0]
            component.play_animation(u.load_asset(outcome['animation']),True)
            outcome['playbackWorld'] = simulation_world.get_path_name()
        ready = elapsed > 10 if frame == 0 else elapsed > first_capture_elapsed + 0.37
        if task is None and ready:
            task = u.AutomationLibrary.take_high_res_screenshot(1600,900,
                str(OUT / ('frame-'+str(frame)+'.png')), camera=camera, delay=1)
        elif task is not None and task.is_task_done():
            path = OUT / ('frame-'+str(frame)+'.png')
            if not path.is_file() or path.stat().st_size < 10000:
                raise RuntimeError('Native hero frame missing')
            positions = capture_bones()
            outcome.setdefault('frames',[]).append(dict(path=str(path), sha256=sha(path), elapsedSeconds=elapsed, bones=positions))
            (OUT / 'partial-render.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),'utf8')
            if frame == 0:
                first_capture = positions
                first_capture_elapsed = elapsed
                frame = 1
                task = None
            else:
                movement = [sum((a-b)**2 for a,b in zip(first['position'],second['position']))**0.5
                    for first,second in zip(first_capture,positions)]
                if max(movement) <= 0.001:
                    raise RuntimeError('Native bone positions did not change during idle playback')
                outcome.update(nativeRenderVerified=True, nativeBoneMotionObserved=True,
                    nativeContinuousPlaybackObserved=True, maximumObservedBoneMovementCm=max(movement))
                (OUT / 'native-render.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),'utf8')
                u.unregister_slate_post_tick_callback(handle)
                u.SystemLibrary.quit_editor()
    except Exception:
        (OUT / 'error.txt').write_text(traceback.format_exc(),'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()
    finally:
        busy = False


try:
    for filename in ('frame-0.png', 'frame-1.png', 'native-render.json'):
        old = OUT / filename
        if old.exists():
            old.rename(OUT / (old.stem + '-previous-' + str(time.time_ns()) + old.suffix))
    previous_error = OUT / 'error.txt'
    if previous_error.exists():
        previous_error.rename(OUT / ('error-' + str(time.time_ns()) + '.txt'))
    if '-HczsHeroReadback' in u.SystemLibrary.get_command_line():
        outcome = json.loads((OUT/'import-readback.json').read_text('utf8'))
        world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        if world.get_path_name().split('.')[0] != outcome['map'] or outcome['characterId'] != HERO:
            raise RuntimeError('Readback must start in this hero comparison map')
        actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
        hero_actors = [a for a in actors if a.get_actor_label() == 'HCZS_Hero'+str(HERO).zfill(3)]
        cameras = [a for a in actors if a.get_actor_label() == 'HCZSInspectionCamera']
        if len(hero_actors) != 1 or len(cameras) != 1:
            raise RuntimeError('Readback actor/camera mapping differs')
        component = hero_actors[0].get_component_by_class(u.SkeletalMeshComponent)
        camera = cameras[0]
        original_map_file = ROOT / 'clients/unreal5 5.8/Content' / (outcome['sourceMap'].removeprefix('/Game/')+'.umap')
        if component.get_editor_property('skeletal_mesh_asset').get_path_name() != outcome['mesh'] or sha(original_map_file) != outcome['sourceMapSha256']:
            raise RuntimeError('Readback mesh or preserved source map changed')
        component.play_animation(u.load_asset(outcome['animation']),True)
        component.set_update_animation_in_editor(True)
    else:
        camera, component, outcome = prepare()
    outcome['engineVersion'] = u.SystemLibrary.get_engine_version()
    u.get_editor_subsystem(u.LevelEditorSubsystem).editor_play_simulate()
    started = time.monotonic()
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    (OUT / 'error.txt').write_text(traceback.format_exc(),'utf8')
    u.SystemLibrary.quit_editor()
