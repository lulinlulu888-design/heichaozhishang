"""Create an isolated city2077 visual map; no battle/session compatibility claim.

Run in a fresh full Editor with -ExecutePythonScript. Existing destinations are
read back only. Source scene, actor assets and tutorial map remain untouched.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
sys.path.insert(0, str(ROOT / 'tools'))
from import_recovered_assets import make_pipeline
from export_elsa_model import split_glb, pack_glb

BASE = ROOT / 'analysis/unreal/city-preview'
MAP = '/Game/Recovered/City/Maps/L_City2077Preview'
DEST = '/Game/Recovered/City/Stage2077'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    import unreal as u
    BASE.mkdir(parents=True, exist_ok=True)
    identity = json.loads((ROOT / 'analysis/battle-visual/city-enemy/identity.json').read_text('utf8'))
    if not identity['reusableGeometryMaterialAndAnimationLibrary'] or identity['sharedEntityId'] != 6605:
        raise ValueError('Source enemy identity not established')
    placement = json.loads((ROOT / 'analysis/battle-visual/city-scenes/battle-placement/report.json').read_text('utf8'))
    player = json.loads((ROOT / 'analysis/battle-visual/city-scenes/player-placement/report.json').read_text('utf8'))
    if player['scene']['rows'][0]['fields']['ScenePath'] != 'scene/city_battle_2/city_battle_2.scn':
        raise ValueError('Source city scene changed')
    source = ROOT / 'analysis/battle-visual/city-scenes/city_battle_2/scene.glb'
    if sha(source.read_bytes()) != 'd90e48dfac744f1c44805acb41621c18beb0933942204e406e1131db4c61988a':
        raise ValueError('Original city geometry changed')
    tutorial = ROOT / 'clients/unreal5 5.8/Content/Recovered/Battle/Maps/L_TutorialBattle.umap'
    before = sha(tutorial.read_bytes())
    subsystem = u.get_editor_subsystem(u.EditorActorSubsystem)
    if u.EditorAssetLibrary.does_asset_exist(MAP):
        world = u.EditorLoadingAndSavingUtils.load_map(MAP)
        if not world:
            raise RuntimeError('Cannot read existing city map')
        applied = False
    else:
        if u.EditorAssetLibrary.list_assets(DEST, True, False):
            raise RuntimeError('Partial city import retained; inspect before retry')
        doc, binary = split_glb(source.read_bytes())
        # Distinct source node names avoid Interchange actor-name collisions.
        for i, node in enumerate(doc['nodes']):
            node['name'] = f'city2077_node_{i}'
        staged = BASE / 'city2077.glb'
        staged.write_bytes(pack_glb(doc, binary))
        world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
        if not world:
            raise RuntimeError('Blank world unavailable')
        pipeline, overrides = make_pipeline(u, {'import_operation': 'scene'})
        params = u.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', False)
        params.set_editor_property('override_pipelines', overrides)
        params.set_editor_property('import_level', u.EditorLevelUtils.get_levels(world)[0])
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        if not manager.import_scene(DEST, u.InterchangeManager.create_source_data(str(staged)), params):
            raise RuntimeError('City scene import failed')
        spatial = list(subsystem.get_all_level_actors())
        assets = u.load_asset('/Game/Recovered/Battle/BattleSceneAssets')
        if not assets:
            raise RuntimeError('Verified actor assets unavailable')
        specs = [('player', player['derived_slots'][0], 'idle_1'),
                 ('enemy', dict(position=placement['derived']['position'],
                                rotation_radians=placement['derived']['rotation_radians'],
                                base_scale=placement['derived']['entity_base_scale']), 'idle')]
        for side, spec, idle in specs:
            x, y, z = spec['position']
            actor = subsystem.spawn_actor_from_class(u.SkeletalMeshActor, u.Vector(x*100, z*100, y*100),
                u.Rotator(pitch=0, yaw=-math.degrees(spec['rotation_radians'][1]), roll=0))
            actor.set_actor_label('City2077_' + side)
            actor.set_editor_property('tags', ['City2077_' + side])
            actor.set_actor_scale3d(u.Vector(*spec['base_scale']))
            component = actor.get_component_by_class(u.SkeletalMeshComponent)
            component.set_skeletal_mesh_asset(assets.get_editor_property(side + '_mesh'))
            component.override_animation_data(assets.get_editor_property(side + '_animations')[idle], True, True, 0, 1)
            component.set_update_animation_in_editor(True)
            component.set_editor_property('cast_shadow', False)
            spatial.append(actor)
        adapter = subsystem.spawn_actor_from_class(u.Actor, u.Vector(0, 0, 0))
        adapter.set_actor_label('City2077_CoordinateAdapter')
        adapter.get_editor_property('root_component').set_mobility(u.ComponentMobility.STATIC)
        for actor in spatial:
            if actor.get_editor_property('root_component') and actor.get_attach_parent_actor() is None:
                actor.attach_to_actor(adapter, '', u.AttachmentRule.KEEP_WORLD, u.AttachmentRule.KEEP_WORLD,
                                      u.AttachmentRule.KEEP_WORLD, False)
        adapter.set_actor_scale3d(u.Vector(-1, 1, 1))
        # Explicit inspection camera; source cinematography has not been restored.
        location, target = u.Vector(0, 800, 0), u.Vector(0, -4500, -650)
        camera = subsystem.spawn_actor_from_class(u.CameraActor, location, u.MathLibrary.find_look_at_rotation(location, target))
        camera.set_actor_label('City2077_InspectionCamera')
        camera.set_editor_property('auto_activate_for_player', u.AutoReceiveInput.PLAYER0)
        camera.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 61.0)
        world.get_world_settings().set_editor_property('default_game_mode', u.GameModeBase)
        for path in u.EditorAssetLibrary.list_assets(DEST, True, False):
            if not u.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
                raise RuntimeError('Failed to save city asset: ' + path)
        if not u.EditorLoadingAndSavingUtils.save_map(world, MAP):
            raise RuntimeError('Failed to save city map')
        applied = True
    actors = list(subsystem.get_all_level_actors())
    labels = [actor.get_actor_label() for actor in actors]
    if any(labels.count(name) != 1 for name in ['City2077_player', 'City2077_enemy', 'City2077_InspectionCamera']):
        raise RuntimeError('City actors missing or duplicated')
    if sha(tutorial.read_bytes()) != before:
        raise RuntimeError('Tutorial map changed unexpectedly')
    return dict(passed=True, applied=applied, map=MAP, actorCount=len(actors), tutorialMapUnchanged=True,
        runtimeBattleReady=False, originalCameraRestored=False, sourceScene=2077,
        limitations=['Static import/readback only; rendered materials not yet inspected.',
                     'Single Elsa slot0; server formation not restored.',
                     'Enemy uses base scale pending source difficulty branch verification.',
                     'No weapon attachment, HUD, city skill dispatch or ultimate integration in this visual map.'])


if __name__ == '__main__':
    import unreal
    try:
        result = main()
    except Exception:
        result = dict(passed=False, error=traceback.format_exc())
        unreal.log_error(result['error'])
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / 'import-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    unreal.SystemLibrary.quit_editor()
