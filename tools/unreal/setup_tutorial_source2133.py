"""Create a separate tutorial map from the recovered source2133 environment.

Offline --plan does not import Unreal. The parent runs -- ExecutePythonScript in
a dedicated UE5.8 Editor with -HczsTutorialSource2133Apply. Never launch an
Editor here, overwrite a destination, save source maps or modify shared assets.
The existing C++ travel target is deliberately outside this script's scope.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'clients/unreal5 5.8'
OUT = ROOT / 'analysis/unreal/tutorial-source2133'
SOURCE = '/Game/Recovered/SourceStages/Maps/L_RuinedCity'
TUTORIAL = '/Game/Recovered/Battle/Maps/L_TutorialBattle'
TARGET = '/Game/Recovered/Battle/Maps/L_TutorialSource2133'
SCENE = 'scene/pszdu_battle_1/pszdu_battle_1.scn'
PINS = {
    'analysis/battle-visual/prologue-theatre/pszdu_battle_1/scene.glb': '56ce6a0565ae113a709c6ab882f93eb91a6e9a6a7ef12b9bd5486f30c93f3828',
    'analysis/battle-visual/prologue-theatre/source/b887b567a0b3244a4b1a.scn': 'e12d873d6e6916effef155f3a1c792b173f3674f93f2e81589fcba5a678bc2c2',
    'analysis/battle-visual/prologue-theatre/pszdu_battle_1/export.json': '8f0135223d15fd5f02d73b68a6d8d7f669503e15dfadc15603a61ddbb1c57ca9',
    'analysis/worldline-ui/data/scene-associations.json': '5b6f0c2988981e8f14fcab7883b0fd0f5b89d3823cb3874abc2c15150189cf65',
    'analysis/first-encounter/battles.json': '6bc45ea0ad9d293395db0194ec65c338be10e9afaffa5fa7fae23cf7aecb9618',
    'analysis/battle-visual/city-scenes/player-placement/report.json': 'da791401d68109172ab3ba8557d47b3351d467275c676703de18b7da3a293e2b',
    'analysis/battle-visual/city-scenes/battle-placement/report.json': '226ce16b3da2b97bff30588289cd3ba0ecb5c3e94e00b73239340d7cb76e878e',
    'analysis/first-encounter/enemy-entity.json': 'c8dd775becf46f5cab224b74f8fd308f0a40d4fceb8d0e0d2f92fd80356a14cf',
}


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def data(path):
    raw = (ROOT / path).read_bytes()
    check(sha(raw) == PINS[path], 'Source evidence changed: ' + path)
    return json.loads(raw)


def row(document, identity):
    found = [entry for entry in document['rows'] if entry['id'] == identity]
    check(len(found) == 1, 'Source row is not unique: ' + str(identity))
    return found[0]


def plan():
    for path, expected in PINS.items():
        check(sha((ROOT / path).read_bytes()) == expected, 'Source evidence changed: ' + path)
    stage = data('analysis/battle-visual/prologue-theatre/pszdu_battle_1/export.json')
    scene = row(data('analysis/worldline-ui/data/scene-associations.json'), 2133)
    battle = row(data('analysis/first-encounter/battles.json'), 5000)
    players = data('analysis/battle-visual/city-scenes/player-placement/report.json')
    monsters = data('analysis/battle-visual/city-scenes/battle-placement/report.json')
    entity = row(data('analysis/first-encounter/enemy-entity.json'), 6605)['fields']
    check(stage['scene'] == SCENE and scene['fields']['ScenePath'] == SCENE
          and stage['meshes'] == stage['instances'] == 3 and stage['textures'] == 2,
          'Not the expected recovered ruined-city environment')
    camera = stage['scope']['sourceCameras']
    check(len(camera) == 1 and camera[0]['Name'] == scene['fields']['DefaultCamera'] == 'camera_1', 'Source camera changed')
    camera = camera[0]
    matrix = [float(value) for value in camera['Transform'].split(',')]
    check(len(matrix) == 16 and matrix[12:15] == [0., 0., 30.]
          and all(abs(matrix[index]) < .000001 for index in (1, 2, 4, 6, 8, 9))
          and matrix[0] < 0 < matrix[5] and matrix[10] < 0, 'Unsupported source camera basis')
    check(battle['fields']['MonsterInfo'] == [{'MonsterID': 991, 'SpawnPointIdx': 0}]
          and battle['fields']['MonsterSpawnIndex'] == 5, 'Original tutorial monster preset changed')
    spawn = monsters['presets'][str(battle['fields']['MonsterSpawnIndex'])][0]
    # This shared report supplies source constants/scripts, NOT city10405's
    # derived placements. Recompute from source2133 + battle5000 here.
    offset = players['offsets']['posData'][0]
    player_entity = row(players['example_entity'], 0)['fields']
    player_position = [a+b for a, b in zip(scene['fields']['PlayerPosition'], offset)]
    player_rotation = [a+b for a, b in zip(player_entity['ROTATION'], players['offsets']['rotData'][0])]
    enemy_rotation = [a+b for a, b in zip(spawn['rot'], entity['ROTATION'])]
    result = dict(schemaVersion=1, sourceSceneId=2133, sourceScene=SCENE, sourceMap=SOURCE,
        targetMap=TARGET, actorTemplateMap=TUTORIAL, sourcePins=PINS, sourceCamera=camera,
        sourceTableFields=scene['field_sources'],
        player=dict(characterId='1', entityId=0, slot=0, position=player_position, rotationRadians=player_rotation,
                    scale=player_entity['SCALE'], idle='idle_1'),
        enemy=dict(monsterId='991', entityId=6605, spawnPreset=5, slot=0, position=spawn['pos'],
                   rotationRadians=enemy_rotation, scale=entity['SCALE'], idle='idle'),
        camera=dict(sourcePosition=matrix[12:15], uePosition=[0., 3000., 0.], yaw=-90.,
                    sourceFov=float(camera['Fov']), assumedVerticalFov=True, aspectRatio=16/9),
        axes=dict(preReflection='source(x,y,z) -> UE(100x,100z,100y)',
                  existingSourceAdapterScale=[-1., 1., 1.], additionalGlobalRotation=0),
        limitations=[
            'The map reuses 3 recovered original environment surfaces, not the missing original scene SFX/probes/shaders.',
            'Single Elsa uses source player slot0; original received posIndex assignment has not been observed.',
            'Monster preset5/slot0 is the source5000 branch; no scene-table default or editor dummy placement is substituted.',
            'FOV45 is treated as vertical using the existing source-stage importer convention; original projection requires video comparison.',
            'Source game runtime, dynamic camera sequencing, entrance choreography and original rendering parity remain unverified.',
            'The current actor/material/animation/weapon/Presentation and shared SceneAssets are reused unchanged.',
            'C++ map travel still needs an explicit integration by the parent; no existing map or shared asset is updated.'])
    result['recipeSha256'] = sha(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())
    return result


def vec(value):
    return [value.x, value.y, value.z]


def transform(value):
    return dict(translation=vec(value.translation), scale=vec(value.scale3d),
                rotation=[value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w])


def close(actual, expected, name, tolerance=.02):
    check(len(actual) == len(expected) and all(math.isfinite(v) for v in actual + expected)
          and max(abs(a-b) for a, b in zip(actual, expected)) <= tolerance, name + ' differs')


def asset_file(path, world=False):
    check(path.startswith('/Game/'), 'Asset outside project content: ' + path)
    return PROJECT / 'Content' / (path[6:].split('.')[0] + ('.umap' if world else '.uasset'))


def main():
    import unreal as u
    recipe = plan()
    check('-HczsTutorialSource2133Apply' in u.SystemLibrary.get_command_line().split(), 'Require -HczsTutorialSource2133Apply in a dedicated Editor')
    check(Path(u.Paths.project_dir()).resolve() == PROJECT.resolve() and u.SystemLibrary.get_engine_version().startswith('5.8.'), 'Wrong project/engine')
    check(not u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world(), 'Do not modify maps during PIE')
    check(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Retain unsaved editor maps before running this setup')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    report = dict(schemaVersion=1, mode='tutorial-source2133-static-map-setup', passed=False, recipe=recipe,
                  startedAtUnixMs=int(time.time()*1000), originalRuntimeExecuted=False, frameVerified=False)
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / ('setup-result-' + str(time.time_ns()) + '.json')
    protected = {}

    def protect(path):
        path = path.resolve()
        check(path.is_relative_to((PROJECT/'Content').resolve()) and path.is_file(), 'Protected input absent: ' + str(path))
        digest = sha(path.read_bytes())
        check(path.as_posix() not in protected or protected[path.as_posix()] == digest, 'Protected asset changed before repeated readback: ' + str(path))
        protected[path.as_posix()] = digest

    def unchanged():
        check(all(Path(path).is_file() and sha(Path(path).read_bytes()) == digest for path, digest in protected.items()),
              'A protected source map/asset changed on disk')

    def unique(tag):
        matches = [actor for actor in actors.get_all_level_actors() if actor.actor_has_tag(tag)]
        check(len(matches) == 1, 'Missing/duplicated actor tag: ' + tag)
        return matches[0]

    def load_map(path):
        world = u.EditorLoadingAndSavingUtils.load_map(path)
        check(world is not None and world.get_path_name().split('.')[0] == path, 'Cannot load exact map: ' + path)
        return world

    def component_refs(actor, side):
        cls = u.StaticMeshComponent if side == 'weapon' else u.SkeletalMeshComponent
        component = actor.get_component_by_class(cls)
        check(component is not None and component.get_num_materials() > 0, 'Missing actual source component: ' + side)
        mesh = component.get_editor_property('static_mesh') if side == 'weapon' else component.get_skeletal_mesh_asset()
        check(mesh is not None, 'Actual mesh asset missing: ' + side)
        refs = dict(mesh=mesh.get_path_name(), materials=[component.get_material(i).get_path_name() for i in range(component.get_num_materials())])
        for path in [refs['mesh']] + refs['materials']:
            protect(asset_file(path))
        return component, refs

    def environment():
        rows = []
        for actor in actors.get_all_level_actors():
            for component in actor.get_components_by_class(u.StaticMeshComponent):
                mesh = component.get_editor_property('static_mesh')
                if mesh and mesh.get_path_name().startswith('/Game/Recovered/SourceStages/RuinedCity/'):
                    materials = []
                    for index in range(component.get_num_materials()):
                        material = component.get_material(index)
                        actual = material.get_path_name()
                        source = actual
                        if actual.startswith('/Game/Recovered/Battle/Source2133Colour/'):
                            # Explicit source-identity normalization for a known
                            # adapter; never claim adapted pixels/material bytes
                            # are equal to the original reference import.
                            sys.path.insert(0, str(ROOT/'tools/unreal'))
                            from apply_tutorial_source2133_colour import source_binding
                            source = source_binding(u, material)
                            adapted = dict(actualMaterial=actual, originalMaterial=source,
                                           validation='owned linear-colour graph; source identity only')
                            report.setdefault('ownedColourBindings', [])
                            if adapted not in report['ownedColourBindings']:
                                report['ownedColourBindings'].append(adapted)
                        materials.append(source)
                    rows.append(dict(label=actor.get_actor_label(), mesh=mesh.get_path_name(),
                        transform=transform(component.get_world_transform()),
                        materials=materials))
        rows.sort(key=lambda value: (value['label'], value['mesh']))
        check(len(rows) == 3, 'Source2133 environment surface inventory differs')
        return rows

    try:
        protect(asset_file(SOURCE, True)); protect(asset_file(TUTORIAL, True))
        for file in (PROJECT/'Content/Recovered/SourceStages/RuinedCity').rglob('*'):
            if file.is_file():
                protect(file)
        load_map(TUTORIAL)
        template = {}
        for side, tag in [('player', 'HCZSBattlePlayer'), ('enemy', 'HCZSBattleEnemy'), ('weapon', 'HCZSBattleWeapon')]:
            actor = unique(tag)
            component, template[side] = component_refs(actor, side)
            if side == 'weapon':
                template[side].update(socket=str(component.get_attach_socket_name()),
                    relativeTransform=transform(component.get_relative_transform()))
                weapon_relative = component.get_relative_transform()
                check(template[side]['socket'] == 'bip001-prop1' and component.get_attach_parent() == unique('HCZSBattlePlayer').get_component_by_class(u.SkeletalMeshComponent),
                      'Template weapon is not attached to the verified original bone')
        scene_assets = unique('HCZSBattlePresentation').get_editor_property('SceneAssets')
        check(scene_assets and scene_assets.get_editor_property('SupportedEncounterId') == 'tutorial-5000'
              and scene_assets.get_editor_property('PlayerId') == '1' and scene_assets.get_editor_property('EnemyId') == '991', 'Wrong shared SceneAssets')
        template['sceneAssets'] = scene_assets.get_path_name()
        protect(asset_file(template['sceneAssets']))
        for side in ('player', 'enemy'):
            animations = scene_assets.get_editor_property(side + '_animations')
            check(recipe[side]['idle'] in animations, 'Original idle is missing: ' + side)
            template[side]['idleAsset'] = animations[recipe[side]['idle']].get_path_name()
            for animation in animations.values():
                protect(asset_file(animation.get_path_name()))
        mode = u.load_class(None, '/Script/Hczs.HczsBattleMode')
        presentation_class = u.load_class(None, '/Script/Hczs.HczsBattlePresentation')
        check(mode and presentation_class, 'Native battle classes are unavailable')
        source_world = load_map(SOURCE)
        source_environment = environment()
        report.update(template=template, sourceEnvironment=source_environment)
        created = not u.EditorAssetLibrary.does_asset_exist(TARGET)
        if created:
            # Save-as first, before any actor edits. The imported source .umap
            # and all source/shared UAssets are guarded byte-for-byte below.
            check(not asset_file(TARGET, True).exists(), 'Unregistered target file already exists')
            check(u.EditorLoadingAndSavingUtils.save_map(source_world, TARGET), 'Cannot copy original environment into new map')
            world = load_map(TARGET)
            adapters = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'HCZSSourceStageAxisAdapter']
            check(len(adapters) == 1, 'Original source-stage adapter is missing/duplicated')
            adapter = adapters[0]
            close(vec(adapter.get_actor_scale3d()), [-1., 1., 1.], 'Existing single axis reflection', .000001)
            close(vec(adapter.get_actor_location()), [0., 0., 0.], 'Existing adapter origin')
            check(abs(adapter.get_actor_rotation().pitch) + abs(adapter.get_actor_rotation().yaw) + abs(adapter.get_actor_rotation().roll) < .00001,
                  'Unexpected additional source-stage rotation')
            adapter.set_actor_label('HCZSBattleCoordinateAdapter')
            adapter.set_editor_property('tags', ['HCZSBattleCoordinateAdapter', 'HCZSTutorialSource2133'])
            combatants = {}
            for side, tag in [('player', 'HCZSBattlePlayer'), ('enemy', 'HCZSBattleEnemy')]:
                spec = recipe[side]
                px, py, pz = spec['position']
                actor = actors.spawn_actor_from_class(u.SkeletalMeshActor, u.Vector(px*100, pz*100, py*100),
                    u.Rotator(pitch=0, yaw=-math.degrees(spec['rotationRadians'][1]), roll=0))
                actor.set_actor_label(tag); actor.set_editor_property('tags', [tag])
                actor.set_actor_scale3d(u.Vector(*spec['scale']))
                check(actor.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE,
                    u.AttachmentRule.KEEP_RELATIVE, False), 'Cannot attach combatant to existing reflection')
                component = actor.get_component_by_class(u.SkeletalMeshComponent)
                component.set_skeletal_mesh_asset(u.load_asset(template[side]['mesh']))
                for index, path in enumerate(template[side]['materials']):
                    component.set_material(index, u.load_asset(path))
                component.override_animation_data(u.load_asset(template[side]['idleAsset']), True, True, 0., 1.)
                component.set_update_animation_in_editor(True)
                component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
                component.set_editor_property('cast_shadow', False)
                combatants[side] = component
            weapon = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
            weapon.set_actor_label('HCZSBattleWeapon'); weapon.set_editor_property('tags', ['HCZSBattleWeapon'])
            component = weapon.get_component_by_class(u.StaticMeshComponent)
            component.set_mobility(u.ComponentMobility.MOVABLE)
            component.set_static_mesh(u.load_asset(template['weapon']['mesh']))
            component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            component.set_editor_property('cast_shadow', False)
            for index, path in enumerate(template['weapon']['materials']):
                component.set_material(index, u.load_asset(path))
            check(combatants['player'].get_bone_index(template['weapon']['socket']) >= 0
                  and component.attach_to_component(combatants['player'], template['weapon']['socket'],
                      u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE, False),
                  'Cannot reuse original weapon attachment')
            component.set_relative_transform(weapon_relative, False, True)
            presentation = actors.spawn_actor_from_class(presentation_class, u.Vector())
            presentation.set_actor_label('HCZSBattlePresentation'); presentation.set_editor_property('tags', ['HCZSBattlePresentation'])
            presentation.set_editor_property('SceneAssets', u.load_asset(template['sceneAssets']))
            cameras = [a for a in actors.get_all_level_actors() if isinstance(a, u.CameraActor)]
            check(len(cameras) == 1 and cameras[0].get_actor_label() == 'HCZSSourceStageCamera', 'Original source-stage inspection camera differs')
            camera = cameras[0]
            camera.set_actor_label('HCZSBattleCamera'); camera.set_editor_property('tags', ['HCZSBattleCamera'])
            camera.set_actor_location(u.Vector(*recipe['camera']['uePosition']), False, False)
            camera.set_actor_rotation(u.Rotator(pitch=0., yaw=-90., roll=0.), False)
            camera.set_editor_property('auto_activate_for_player', u.AutoReceiveInput.PLAYER0)
            cc = camera.get_component_by_class(u.CameraComponent)
            hfov = math.degrees(2*math.atan(math.tan(math.radians(recipe['camera']['sourceFov'])/2)*recipe['camera']['aspectRatio']))
            cc.set_editor_property('field_of_view', hfov)
            cc.set_editor_property('aspect_ratio', recipe['camera']['aspectRatio'])
            cc.set_editor_property('constrain_aspect_ratio', True)
            world.get_world_settings().set_editor_property('default_game_mode', mode)
            world.get_world_settings().set_editor_property('force_no_precomputed_lighting', True)
            check(environment() == source_environment, 'Original environment geometry/material bindings changed while adding actors')
            check(u.EditorLoadingAndSavingUtils.save_map(world, TARGET), 'Cannot save independent tutorial map')
        world = load_map(TARGET)
        check(unique('HCZSTutorialSource2133') == unique('HCZSBattleCoordinateAdapter'), 'Unowned or incomplete existing destination retained')
        check(environment() == source_environment, 'Saved source environment differs')
        adapter = unique('HCZSBattleCoordinateAdapter')
        close(vec(adapter.get_actor_scale3d()), [-1., 1., 1.], 'Single persisted reflection', .000001)
        check(world.get_world_settings().get_editor_property('default_game_mode') == mode, 'Saved battle mode differs')
        check(unique('HCZSBattlePresentation').get_editor_property('SceneAssets').get_path_name() == template['sceneAssets'], 'Shared SceneAssets changed')
        camera = unique('HCZSBattleCamera')
        cc = camera.get_component_by_class(u.CameraComponent)
        camera_axes = dict(position=vec(cc.get_world_transform().translation), forward=vec(cc.get_forward_vector()),
            right=vec(cc.get_right_vector()), up=vec(cc.get_up_vector()), horizontal_fov=cc.get_editor_property('field_of_view'),
            aspect_ratio=cc.get_editor_property('aspect_ratio'))
        close(vec(camera.get_actor_location()), recipe['camera']['uePosition'], 'Source camera position')
        close(vec(cc.get_forward_vector()), [0., -1., 0.], 'Source camera direction', .000001)
        expected_fov = math.degrees(2*math.atan(math.tan(math.radians(recipe['camera']['sourceFov'])/2)*recipe['camera']['aspectRatio']))
        check(abs(camera_axes['horizontal_fov']-expected_fov) < .00001
              and abs(camera_axes['aspect_ratio']-recipe['camera']['aspectRatio']) < .000001
              and cc.get_editor_property('constrain_aspect_ratio'), 'Persisted source camera FOV/aspect differs')
        sys.path.insert(0, str(ROOT/'tools/unreal'))
        from verify_battle_scene import project
        readback = {}
        for side, tag in [('player', 'HCZSBattlePlayer'), ('enemy', 'HCZSBattleEnemy')]:
            actor = unique(tag); component, refs = component_refs(actor, side)
            check(actor.get_attach_parent_actor() == adapter and refs == {key: template[side][key] for key in ('mesh', 'materials')},
                  'Actor asset/material/parent differs: ' + side)
            px, py, pz = recipe[side]['position']
            close(vec(actor.get_actor_location()), [-px*100, pz*100, py*100], 'Persisted source slot: ' + side)
            close(vec(actor.get_editor_property('root_component').get_relative_transform().scale3d), recipe[side]['scale'], 'Persisted source actor scale: ' + side, .000001)
            readback[side] = dict(refs, worldTransform=transform(actor.get_actor_transform()), projection=project(vec(actor.get_actor_location()), camera_axes))
        check(readback['player']['projection']['inside'] and readback['enemy']['projection']['inside']
              and readback['player']['projection']['uv'][0] < readback['enemy']['projection']['uv'][0], 'Source camera no longer puts player left of enemy inside frame')
        weapon_component, refs = component_refs(unique('HCZSBattleWeapon'), 'weapon')
        check(refs == {key: template['weapon'][key] for key in ('mesh', 'materials')}
              and weapon_component.get_attach_parent() == unique('HCZSBattlePlayer').get_component_by_class(u.SkeletalMeshComponent)
              and str(weapon_component.get_attach_socket_name()) == template['weapon']['socket'], 'Persisted original weapon binding differs')
        relative = transform(weapon_component.get_relative_transform())
        for key in ('translation', 'scale'):
            close(relative[key], template['weapon']['relativeTransform'][key], 'Persisted weapon ' + key, .000001)
        q, expected_q = relative['rotation'], template['weapon']['relativeTransform']['rotation']
        check(min(max(abs(a-b) for a, b in zip(q, expected_q)), max(abs(a+b) for a, b in zip(q, expected_q))) < .000001,
              'Persisted weapon relative rotation differs')
        unchanged()
        report.update(passed=True, created=created, map=TARGET, mapSha256=sha(asset_file(TARGET, True).read_bytes()),
            protectedFiles=protected, protectedFilesUnchanged=True, nativeStaticReadback=readback,
            camera=camera_axes, environment=source_environment, sourceSfxRestored=False,
            originalCameraProjectionVerified=False, currentRuntimeTravelChanged=False)
    except Exception:
        report['error'] = traceback.format_exc()
        try:
            unchanged()
            report['protectedFilesUnchanged'] = True
        except Exception:
            report['protectedFilesUnchanged'] = False
        raise
    finally:
        report['finishedAtUnixMs'] = int(time.time()*1000)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
        u.log('HCZS source2133 setup report: ' + str(report_path))


if __name__ == '__main__':
    if '--plan' in sys.argv:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, allow_nan=False))
    else:
        main()
