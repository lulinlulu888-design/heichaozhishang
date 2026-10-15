"""Full UE5.8 Editor import/map setup for the marked local tutorial reconstruction.

Run after prepare_battle_inputs.py and a successful Hczs Editor C++ build using
-ExecutePythonScript. Never launch UE from this script, never change hall maps.
The new map is saved only after source/input/class/animation checks succeed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/unreal/battle-inputs'
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import read_glb, glb_summary, make_pipeline, object_summary

MAPPING_PINS = {
    'analysis/battle-visual/skill-animation/mapping.json': 'e2f5a56d6db599c71fc128562b1681ca8b809f37cb917fecab8abac251fbc7d0',
    'analysis/first-encounter/skill-timelines.json': '33187be72b2b1d65854dc4852dac72ef3dfe562b985c4234584c1873b7741243',
    'analysis/first-encounter/enemy-entity.json': 'c8dd775becf46f5cab224b74f8fd308f0a40d4fceb8d0e0d2f92fd80356a14cf',
}
SCENE_ASSET = '/Game/Recovered/Battle/BattleSceneAssets'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(report):
    (BASE / 'import-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')


def archive_previous_report():
    """Keep each previous attempt byte-for-byte before publishing a new report."""
    path = BASE / 'import-result.json'
    if not path.exists():
        return None
    raw = path.read_bytes()
    folder = BASE / 'import-attempts'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('report-' + digest(raw)[:20] + '.json')
    if target.exists() and target.read_bytes() != raw:
        raise RuntimeError('Existing archived import report has different bytes')
    if not target.exists():
        target.write_bytes(raw)
    return target.relative_to(ROOT).as_posix()


def new_scene_destination(unreal, row):
    """Never reuse/delete partial scene imports: validate and retain their assets.

    Interchange saved assets do not repopulate a newly created actor world by
    themselves. A fresh namespace is safer than inventing node->asset mappings.
    """
    original = row['import_path']
    retained = []
    number = 1
    while number <= 32:
        destination = original if number == 1 else original + '_Attempt' + str(number)
        objects = asset_objects(unreal, destination)
        if not objects:
            return destination, retained
        if any(unreal.EditorAssetLibrary.get_metadata_tag(obj, 'HczsBattleInputSHA256') != row['sha256']
               for obj in objects):
            raise RuntimeError('Retained scene namespace contains unverified/user assets: ' + destination)
        retained.append(dict(destination=destination, sha256=row['sha256'],
                             assets=[object_summary(obj) for obj in objects], policy='retained unchanged'))
        number += 1
    raise RuntimeError('Too many retained scene attempts; inspect before allocating another')


def verified_plan():
    raw = (BASE / 'manifest.json').read_bytes()
    manifest = json.loads(raw)
    if manifest['schema'] != 'hczs-unreal-battle-inputs-v1' or len(manifest['assets']) != 4:
        raise ValueError('Unsupported battle handoff')
    if manifest['map'] != '/Game/Recovered/Battle/Maps/L_TutorialBattle':
        raise ValueError('Battle map destination changed')
    layout_bytes = (BASE / manifest['layout_file']).read_bytes()
    if digest(layout_bytes) != manifest['layout_sha256']:
        raise ValueError('Battle source layout changed')
    rows = []
    for record in manifest['assets']:
        if not record['import_path'].startswith('/Game/Recovered/Battle/'):
            raise ValueError('Import destination outside dedicated battle content')
        path = (BASE / record['file']).resolve()
        if not path.is_relative_to(BASE.resolve()):
            raise ValueError('Staged file escapes handoff')
        payload = path.read_bytes()
        source = (ROOT / record['source_file']).resolve()
        if not source.is_relative_to(ROOT.resolve()) or digest(source.read_bytes()) != record['source_sha256']:
            raise ValueError('Original recovered asset changed')
        if digest(payload) != record['sha256'] or len(payload) != record['bytes']:
            raise ValueError('Battle staged asset hash mismatch')
        doc = read_glb(payload)
        if glb_summary(doc) != record['geometry']:
            raise ValueError('Battle GLB inventory changed')
        for entry in doc.get('buffers', []) + doc.get('images', []):
            if entry.get('uri') and not entry['uri'].startswith('data:'):
                raise ValueError('Unexpected external GLB URI')
        rows.append({**record, 'filename': path.as_posix(), 'source_document': doc})
    mapping_sources = {}
    for path, expected in MAPPING_PINS.items():
        payload = (ROOT / path).read_bytes()
        if digest(payload) != expected:
            raise ValueError('Source animation mapping evidence changed: ' + path)
        mapping_sources[path] = json.loads(payload)
    cards = {str(link['timeline']['fields']['OwnerSkill']): link['clip_names']
             for link in mapping_sources['analysis/battle-visual/skill-animation/mapping.json']['links']}
    if cards != {'110001':['fire_1'], '110009':['crit_1'], '210003':['fire_1'],
                 '410101':['fire_1_1','fire_1_3','fire_2'], '410102':['fire_1']}:
        raise ValueError('Reviewed source card timeline mapping changed')
    # The source list has three candidates, but this card's recovered reactCount
    # is two; existing audited reconstruction uses its first two full clips.
    cards['410101'] = cards['410101'][:2]
    entity = mapping_sources['analysis/first-encounter/enemy-entity.json']['rows'][0]['fields']
    enemy = {}
    for row in mapping_sources['analysis/first-encounter/skill-timelines.json']['rows']:
        if row['id'] not in (558, 559, 560):
            continue
        states = row['fields']['DATA']['ANIMATION_LIST']
        if len(states) != 1:
            raise ValueError('Enemy source timeline is not a single known animation')
        enemy[str(row['fields']['OwnerSkill'])] = entity['ANIM_STATES_' + states[0]]
    if enemy != {'990':'fire', '991':'skill_2', '992':'skill_3'}:
        raise ValueError('Reviewed enemy source timeline/entity mapping changed')
    mapping = dict(source_pins=MAPPING_PINS, card_animation_queues=cards, enemy_skill_clips=enemy,
                   policy='source clip mapping with two full clips for reactCount=2 card410101; receipt-order visual choreography reconstructed',
                   original_hit_timing_verified=False)
    mapping_raw = json.dumps(mapping, ensure_ascii=False, indent=2, allow_nan=False).encode('utf8')
    (BASE/'animation-mapping.json').write_bytes(mapping_raw)
    return dict(manifest_sha256=digest(raw), rows=rows, map=manifest['map'], layout=json.loads(layout_bytes),
                mapping=mapping, mapping_sha256=digest(mapping_raw), limitations=manifest['limitations'])


def asset_objects(unreal, destination):
    return [obj for obj in (unreal.load_asset(path) for path in
            unreal.EditorAssetLibrary.list_assets(destination, True, False)) if obj is not None]


def map_animations(animations, source_document):
    result = {}
    for source in source_document['animations']:
        name = source['name']
        matches = [anim for anim in animations if anim.get_name().lower().endswith(name.lower())]
        # fire_1 has no suffix collision with fire_1_1 / fire_1_3.
        if len(matches) != 1:
            raise RuntimeError('Imported animation name is ambiguous/missing: ' + name + '; actual=' + str([a.get_name() for a in animations]))
        times = source_document['accessors'][source['samplers'][0]['input']]
        expected = times['max'][0]
        actual = matches[0].get_play_length()
        if abs(actual - expected) > 1e-4:
            raise RuntimeError('Imported animation duration changed: ' + name)
        result[name] = matches[0]
    if len(set(a.get_path_name() for a in result.values())) != len(result):
        raise RuntimeError('Multiple source clips resolved to one imported animation')
    return result


def main():
    plan = verified_plan()
    previous_report = archive_previous_report()
    report = dict(schema='hczs-unreal-battle-import-v1', manifest_sha256=plan['manifest_sha256'],
                  map=plan['map'], results=[], limitations=plan['limitations'], passed=False,
                  original_tutorial_stage_recovered=False, gameplay_loop_verified=False,
                  native_platforms_verified=False, previous_report=previous_report,
                  retained_partial_scene_imports=[])
    write(report)
    try:
        import unreal
        report['engine_version'] = unreal.SystemLibrary.get_engine_version()
        actual_project = Path(unreal.Paths.get_project_file_path()).resolve()
        expected_project = (ROOT / 'clients/unreal5 5.8/Hczs.uproject').resolve()
        if actual_project != expected_project or not report['engine_version'].startswith('5.8.'):
            raise RuntimeError('Must run inside the current converted Hczs UE5.8 project')
        if unreal.EditorAssetLibrary.does_asset_exist(plan['map']):
            raise RuntimeError('Dedicated battle map already exists; retain it and audit rather than overwrite')
        mode_path = os.environ.get('HCZS_UE_BATTLE_MODE', '/Script/Hczs.HczsBattleMode')
        if not mode_path.startswith('/Script/Hczs.'):
            raise ValueError('Only project-owned game mode classes are allowed')
        mode = unreal.load_class(None, mode_path)
        if not mode:
            raise RuntimeError('Compile the real battle GameMode first: ' + mode_path)
        presentation_class = unreal.load_class(None, '/Script/Hczs.HczsBattlePresentation')
        if not presentation_class or not hasattr(unreal, 'HczsBattleSceneAssets') or not hasattr(unreal, 'HczsBattleAnimationSequence'):
            raise RuntimeError('Compile the typed battle scene presentation classes first')
        if unreal.EditorAssetLibrary.does_asset_exist(SCENE_ASSET):
            raise RuntimeError('Existing scene DataAsset retained; audit before changing it')
        stage_row = next(row for row in plan['rows'] if row['id'] == 'stage')
        stage_destination, retained = new_scene_destination(unreal, stage_row)
        report['retained_partial_scene_imports'] = retained
        report['new_scene_import_destination'] = stage_destination
        write(report)
        world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
        if not world:
            raise RuntimeError('Cannot create dedicated blank battle map')
        manager = unreal.InterchangeManager.get_interchange_manager_scripted()
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        imported = {}
        imported_scene_actors = []
        # Check skeletal assets and their actual sequence names before importing
        # the environment, so an animation naming failure has a narrow retry.
        ordered_rows = sorted(plan['rows'], key=lambda row: row['import_operation'] == 'scene')
        for row in ordered_rows:
            # Only the fresh scene destination changes on retry; original input
            # identity and all previously saved namespaces remain untouched.
            if row['import_operation'] == 'scene':
                row = {**row, 'import_path':stage_destination}
            objects = asset_objects(unreal, row['import_path'])
            if objects:
                if row['import_operation'] == 'scene':
                    raise RuntimeError('Partial scene import exists; retain and inspect before retry: ' + row['import_path'])
                if any(unreal.EditorAssetLibrary.get_metadata_tag(obj, 'HczsBattleInputSHA256') != row['sha256'] for obj in objects):
                    raise RuntimeError('Existing battle assets have different/unverified sources')
                succeeded = True
            else:
                source = unreal.InterchangeManager.create_source_data(row['filename'])
                params = unreal.ImportAssetParameters()
                params.set_editor_property('is_automated', True)
                params.set_editor_property('replace_existing', False)
                pipeline, pipelines = make_pipeline(unreal, row)
                params.set_editor_property('override_pipelines', pipelines)
                if row['import_operation'] == 'scene':
                    before_scene_actor_paths = {actor.get_path_name() for actor in actors.get_all_level_actors()}
                    params.set_editor_property('import_level', unreal.EditorLevelUtils.get_levels(world)[0])
                    succeeded = manager.import_scene(row['import_path'], source, params)
                else:
                    response = manager.import_asset(row['import_path'], source, params)
                    succeeded = response[0] if isinstance(response, tuple) else response
                if not succeeded:
                    raise RuntimeError('Interchange rejected source: ' + row['id'])
                objects = asset_objects(unreal, row['import_path'])
                if not objects:
                    raise RuntimeError('Import returned no assets')
                for obj in objects:
                    unreal.EditorAssetLibrary.set_metadata_tag(obj, 'HczsBattleInputSHA256', row['sha256'])
                    if not unreal.EditorAssetLibrary.save_loaded_asset(obj, False):
                        raise RuntimeError('Imported battle asset save failed')
                if row['import_operation'] == 'scene':
                    imported_scene_actors = [actor for actor in actors.get_all_level_actors()
                                            if actor.get_path_name() not in before_scene_actor_paths]
                    if not imported_scene_actors:
                        raise RuntimeError('Scene import produced assets without native scene actors')
                    report['imported_scene_actor_inventory'] = [dict(path=actor.get_path_name(),
                        label=actor.get_actor_label(), class_name=actor.get_class().get_name(),
                        root_component=actor.get_editor_property('root_component').get_path_name() if actor.get_editor_property('root_component') else None,
                        attach_parent=actor.get_attach_parent_actor().get_path_name() if actor.get_attach_parent_actor() else None)
                        for actor in imported_scene_actors]
            imported[row['id']] = objects
            if row['id'] in ('player', 'enemy'):
                sequences = [obj for obj in objects if isinstance(obj, unreal.AnimSequence)]
                map_animations(sequences, row['source_document'])
            report['results'].append(dict(id=row['id'], sha256=row['sha256'], import_path=row['import_path'],
                                          assets=[object_summary(obj) for obj in objects]))
            write(report)
        layout = plan['layout']
        combatants = {}
        actual_animation_maps = {}
        actual_meshes = {}
        for identifier in ('player', 'enemy'):
            meshes = [obj for obj in imported[identifier] if isinstance(obj, unreal.SkeletalMesh)]
            animations = [obj for obj in imported[identifier] if isinstance(obj, unreal.AnimSequence)]
            source = next(row['source_document'] for row in plan['rows'] if row['id'] == identifier)
            if len(meshes) != 1:
                raise RuntimeError('Expected exactly one source skeletal mesh: ' + identifier)
            mapping = map_animations(animations, source)
            actual_animation_maps[identifier] = mapping
            actual_meshes[identifier] = meshes[0]
            spec = layout[identifier]
            px, py, pz = spec['position']
            rotation = unreal.Rotator(pitch=0, yaw=-math.degrees(spec['rotation_radians'][1]), roll=0)
            actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(px*100, pz*100, py*100), rotation)
            tag = layout['actor_tags'][identifier]
            actor.set_actor_label(tag)
            actor.set_editor_property('tags', [tag])
            actor.set_actor_scale3d(unreal.Vector(*spec['scale']))
            component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            component.set_skeletal_mesh_asset(meshes[0])
            component.override_animation_data(mapping[spec['normal_idle']], True, True, 0, 1)
            component.set_update_animation_in_editor(True)
            component.set_editor_property('cast_shadow', False)
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            combatants[identifier] = (actor, component)
            report[identifier] = dict(actor=actor.get_path_name(), tag=tag, mesh=meshes[0].get_path_name(),
                                      bone_count=component.get_num_bones(), idle_clip=spec['normal_idle'],
                                      animations={name: anim.get_path_name() for name, anim in mapping.items()})
        weapon_meshes = [obj for obj in imported['weapon'] if isinstance(obj, unreal.StaticMesh)]
        if len(weapon_meshes) != 1:
            raise RuntimeError('Expected one rigid weapon surface mesh')
        weapon = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        weapon.set_actor_label(layout['actor_tags']['weapon'])
        weapon.set_editor_property('tags', [layout['actor_tags']['weapon']])
        component = weapon.get_component_by_class(unreal.StaticMeshComponent)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        component.set_static_mesh(weapon_meshes[0])
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_editor_property('cast_shadow', False)
        player_component = combatants['player'][1]
        bone = layout['weapon_attachment']['ue_bone']
        if player_component.get_bone_index(bone) < 0:
            raise RuntimeError('Imported source weapon attachment bone missing: ' + bone)
        if not component.attach_to_component(player_component, bone, unreal.AttachmentRule.SNAP_TO_TARGET,
                                              unreal.AttachmentRule.SNAP_TO_TARGET, unreal.AttachmentRule.SNAP_TO_TARGET, False):
            raise RuntimeError('Rigid source weapon component attachment failed')
        report['weapon'] = dict(actor=weapon.get_path_name(), mesh=weapon_meshes[0].get_path_name(), bone=bone,
                                attachment_policy=layout['weapon_attachment']['policy'], native_semantics_verified=False)
        # Keep the one source camera-axis adaptation explicit and reversible.
        owned_spatial = imported_scene_actors + [pair[0] for pair in combatants.values()]
        owned_paths = {actor.get_path_name() for actor in owned_spatial}
        roots = []
        for actor in owned_spatial:
            if not actor.get_editor_property('root_component'):
                continue
            parent = actor.get_attach_parent_actor()
            if parent and parent.get_path_name() not in owned_paths:
                raise RuntimeError('Source actor unexpectedly attached outside scene import: ' + actor.get_actor_label())
            if parent is None:
                roots.append(actor)
        report['coordinate_adapter_source_roots'] = [actor.get_path_name() for actor in roots]
        if not roots or any(pair[0] not in roots for pair in combatants.values()):
            raise RuntimeError('Source spatial roots/combatants incomplete before reflection')
        adapter = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
        adapter.set_actor_label('HCZSBattleCoordinateAdapter')
        adapter.set_editor_property('tags', ['HCZSBattleCoordinateAdapter'])
        adapter_root = adapter.get_editor_property('root_component')
        if not adapter_root:
            raise RuntimeError('Editor EmptyActor factory did not create a scene root')
        # Source environment root is static. UE rejects attaching a static
        # source child to the EmptyActor factory's default movable root. The
        # adapter is fixed after this one editor-time reflection; use a static
        # parent and preserve source environment mobility. Movable skeletal
        # combatants may attach to this static parent normally.
        adapter_root.set_mobility(unreal.ComponentMobility.STATIC)
        report['coordinate_adapter_mobility'] = 'STATIC; one editor-time reflection only'
        for actor in roots:
            actor.attach_to_actor(adapter, '', unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                                  unreal.AttachmentRule.KEEP_WORLD, False)
            if actor.get_attach_parent_actor() != adapter:
                raise RuntimeError('Source axis adaptation failed: ' + actor.get_actor_label())
        adapter.set_actor_scale3d(unreal.Vector(*layout['coordinates']['after_import_world_reflection']))
        spec = layout['camera']
        def converted(position):
            x, y, z = position
            return unreal.Vector(-x*100, z*100, y*100)
        location, target = converted(spec['inspection_position']), converted(spec['inspection_target'])
        rotation = unreal.MathLibrary.find_look_at_rotation(location, target)
        camera = actors.spawn_actor_from_class(unreal.CameraActor, location, rotation)
        camera.set_actor_label(spec['primary_tag'])
        camera.set_editor_property('tags', [spec['primary_tag']])
        camera_component = camera.get_component_by_class(unreal.CameraComponent)
        horizontal_fov = math.degrees(2*math.atan(math.tan(math.radians(spec['vertical_fov'])/2)*spec['aspect_ratio']))
        camera_component.set_editor_property('field_of_view', horizontal_fov)
        camera_component.set_editor_property('aspect_ratio', spec['aspect_ratio'])
        camera_component.set_editor_property('constrain_aspect_ratio', True)
        # Native reflected UPROPERTY names are used verbatim to avoid Python
        # acronym-conversion differences. Store imported UObject references,
        # never assume a generated animation asset's filename/suffix at runtime.
        scene_assets = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'BattleSceneAssets', '/Game/Recovered/Battle', unreal.HczsBattleSceneAssets, unreal.DataAssetFactory())
        if not scene_assets:
            raise RuntimeError('Cannot create typed original-resource scene DataAsset')
        for key, value in {
            'SourceManifestSHA256':plan['manifest_sha256'], 'SourceMappingSHA256':plan['mapping_sha256'],
            'SceneNotice':'Recovered Elsa/cube resources on city_battle_1 local stage adaptation. Battle5000 base scene2081 and maze3997 override2133 have unverified loading precedence. Original tutorial stage, shaders, hit timing and VFX remain incomplete.',
            'SupportedEncounterId':'tutorial-5000', 'PlayerId':'1', 'EnemyId':'991',
            'PlayerMesh':actual_meshes['player'], 'EnemyMesh':actual_meshes['enemy'],
            'PlayerAnimations':actual_animation_maps['player'], 'EnemyAnimations':actual_animation_maps['enemy'],
            'EnemySkillClips':plan['mapping']['enemy_skill_clips'], 'bOriginalTutorialStageRecovered':False,
        }.items():
            scene_assets.set_editor_property(key, value)
        queues = {}
        for card_id, clip_names in plan['mapping']['card_animation_queues'].items():
            if any(name not in actual_animation_maps['player'] for name in clip_names):
                raise RuntimeError('Mapped original card clip missing from actual import')
            sequence = unreal.HczsBattleAnimationSequence()
            sequence.set_editor_property('Clips', clip_names)
            queues[card_id] = sequence
        scene_assets.set_editor_property('CardAnimationQueues', queues)
        unreal.EditorAssetLibrary.set_metadata_tag(scene_assets, 'HczsBattleInputSHA256', plan['manifest_sha256'])
        if not unreal.EditorAssetLibrary.save_loaded_asset(scene_assets, False):
            raise RuntimeError('Typed scene DataAsset save failed')
        presentation = actors.spawn_actor_from_class(presentation_class, unreal.Vector(0, 0, 0))
        presentation.set_actor_label('HCZSBattlePresentation')
        presentation.set_editor_property('tags', ['HCZSBattlePresentation'])
        presentation.set_editor_property('SceneAssets', scene_assets)
        report['scene_data_asset'] = dict(path=scene_assets.get_path_name(), source_mapping_sha256=plan['mapping_sha256'],
            player_animation_refs={name:anim.get_path_name() for name,anim in actual_animation_maps['player'].items()},
            enemy_animation_refs={name:anim.get_path_name() for name,anim in actual_animation_maps['enemy'].items()},
            card_queues=plan['mapping']['card_animation_queues'], enemy_skills=plan['mapping']['enemy_skill_clips'],
            presentation_actor=presentation.get_path_name(), original_tutorial_stage_recovered=False)
        world.get_world_settings().set_editor_property('default_game_mode', mode)
        world.get_world_settings().set_editor_property('force_no_precomputed_lighting', True)
        report['camera'] = dict(tag=spec['primary_tag'], position=[location.x, location.y, location.z],
                                rotation=dict(pitch=rotation.pitch, yaw=rotation.yaw, roll=rotation.roll),
                                horizontal_fov=horizontal_fov, vertical_fov=spec['vertical_fov'],
                                original_projection_verified=False)
        report['placement'] = dict(player_world_x=combatants['player'][0].get_actor_location().x,
                                    enemy_world_x=combatants['enemy'][0].get_actor_location().x,
                                    axis_adapter_scale=layout['coordinates']['after_import_world_reflection'])
        from verify_battle_scene import project, vec
        camera_axes = dict(position=vec(camera_component.get_world_transform().translation),
            forward=vec(camera_component.get_forward_vector()), right=vec(camera_component.get_right_vector()),
            up=vec(camera_component.get_up_vector()), horizontal_fov=camera_component.get_editor_property('field_of_view'),
            aspect_ratio=camera_component.get_editor_property('aspect_ratio'))
        projected = {side:project(vec(pair[0].get_actor_location()),camera_axes) for side,pair in combatants.items()}
        report['primary_camera_projection'] = dict(camera_axes=camera_axes, combatant_origins=projected,
            proof='actual camera right/up/forward dot products; UV within constrained camera frame')
        if not all(row['inside'] for row in projected.values()) or projected['player']['uv'][0] >= projected['enemy']['uv'][0]:
            raise RuntimeError('Own side must be left of enemy in the primary camera')
        if not unreal.EditorLoadingAndSavingUtils.save_map(world, plan['map']):
            raise RuntimeError('Battle map save failed')
        verified_plan()
        report.update(passed=True, map_saved=True, game_mode=mode_path,
                      actor_count=len(actors.get_all_level_actors()), visible_render_verified=False)
        write(report)
        unreal.log('HCZS original-resource local tutorial scene prepared: ' + str(BASE / 'import-result.json'))
    except Exception:
        report['error'] = traceback.format_exc()
        write(report)
        raise


if __name__ == '__main__':
    main()
