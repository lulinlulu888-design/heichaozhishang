"""Bind verified city clips to an independent DataAsset and presentation actor.

Does not open the public encounter gate; ultimate/BUFF choreography must be
connected and tested before the existing tutorial-only selection is relaxed.
"""
import hashlib
import json
from pathlib import Path
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/unreal/city-preview'
MAP = '/Game/Recovered/City/Maps/L_City2077Preview'
DEST = '/Game/Recovered/City/CityBattleSceneAssets'


def main():
    raw = (BASE / 'skill-mapping.json').read_bytes()
    plan = json.loads(raw)
    if plan['schema'] != 'hczs-city-skill-animation-v1' or plan['enemyId'] != '6605':
        raise RuntimeError('Unsupported city mapping')
    expected = {'66051': 'fire', '66052': 'fire', '66053': 'skill_3', '66054': 'skill_2'}
    if plan['clips'] != expected:
        raise RuntimeError('City source mapping changed')
    source = u.load_asset('/Game/Recovered/Battle/BattleSceneAssets')
    animations = source.get_editor_property('enemy_animations')
    skeleton = source.get_editor_property('enemy_mesh').get_editor_property('skeleton')
    for clip in expected.values():
        animation = animations[clip]
        if animation.get_editor_property('skeleton') != skeleton or animation.get_play_length() <= 0:
            raise RuntimeError('Incompatible city source clip: ' + clip)
    world = u.EditorLoadingAndSavingUtils.load_map(MAP)
    if not world:
        raise RuntimeError('City visual map missing')
    apply = '-HczsBindCityApply' in u.SystemLibrary.get_command_line()
    if apply:
        if u.EditorAssetLibrary.does_asset_exist(DEST):
            raise RuntimeError('Destination exists; read-only verification required')
        asset = u.EditorAssetLibrary.duplicate_asset(source.get_path_name(), DEST)
        asset.set_editor_property('supported_encounter_id', plan['encounter'])
        asset.set_editor_property('enemy_id', plan['enemyId'])
        asset.set_editor_property('enemy_skill_clips', expected)
        asset.set_editor_property('source_mapping_sha256', hashlib.sha256(raw).hexdigest())
        asset.set_editor_property('scene_notice', '城市原场景与动作；规则重建，原镜头/特效未完成')
        if not u.EditorAssetLibrary.save_loaded_asset(asset, False):
            raise RuntimeError('City DataAsset save failed')
        subsystem = u.get_editor_subsystem(u.EditorActorSubsystem)
        actors = list(subsystem.get_all_level_actors())
        for label, tag in [('City2077_player','HCZSBattlePlayer'), ('City2077_enemy','HCZSBattleEnemy'),
                           ('City2077_weapon','HCZSBattleWeapon'), ('City2077_InspectionCamera','HCZSBattleCamera')]:
            matches = [a for a in actors if a.get_actor_label() == label]
            if len(matches) != 1:
                raise RuntimeError('City actor missing: ' + label)
            tags = list(matches[0].get_editor_property('tags'))
            if tag not in [str(t) for t in tags]:
                tags.append(tag)
            matches[0].set_editor_property('tags', tags)
        presentation = subsystem.spawn_actor_from_class(u.load_class(None, '/Script/Hczs.HczsBattlePresentation'), u.Vector(0,0,0))
        presentation.set_editor_property('tags', ['HCZSBattlePresentation'])
        presentation.set_editor_property('scene_assets', asset)
        if not u.EditorLoadingAndSavingUtils.save_map(world, MAP):
            raise RuntimeError('City presentation map save failed')
    asset = u.load_asset(DEST)
    if not asset or dict(asset.get_editor_property('enemy_skill_clips')) != expected or asset.get_editor_property('enemy_id') != '6605':
        raise RuntimeError('City mapping readback failed')
    if asset.get_editor_property('source_mapping_sha256') != hashlib.sha256(raw).hexdigest():
        raise RuntimeError('City mapping digest mismatch')
    if source.get_editor_property('enemy_id') != '991':
        raise RuntimeError('Tutorial source DataAsset changed')
    if '-HczsCityModeApply' in u.SystemLibrary.get_command_line():
        # The visual-only GameModeBase spawns an unrelated DefaultPawn sphere.
        # Project battle mode has no default pawn and uses the tagged scene camera.
        mode = u.load_class(None, '/Script/Hczs.HczsBattleMode')
        if not mode:
            raise RuntimeError('Project battle mode missing')
        world.get_world_settings().set_editor_property('default_game_mode', mode)
        if not u.EditorLoadingAndSavingUtils.save_map(world, MAP):
            raise RuntimeError('City battle mode save failed')
    return dict(passed=True, applied=apply, asset=DEST, clips=expected, publicEncounterEnabled=False,
                ultimateIntegrated=False, originalEffectsRestored=False)


try:
    result = main()
except Exception:
    result = dict(passed=False, error=traceback.format_exc())
    u.log_error(result['error'])
(BASE / 'binding-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
u.SystemLibrary.quit_editor()
