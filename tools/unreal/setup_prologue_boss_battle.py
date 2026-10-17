"""Build the prologue 3998/1703 party battle map from the recovered boss theatre.

Run in a dedicated UE5.8 Editor with -HczsPrologueBossApply:
  -ExecCmds="py D:/hczs/tools/unreal/setup_prologue_boss_battle.py"
L_Theatre, L_TutorialBattle and the tutorial BattleSceneAssets are read-only
inputs (guarded byte-for-byte). Only the owned map and DataAsset are rebuilt.
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
PROJECT = ROOT / 'clients/unreal5 5.8'
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from preview_prologue_boss import import_boss, import_future_glb, source_placement, to_ue, SCENE_SHA

OUT = ROOT / 'analysis/unreal/prologue-boss-1703'
THEATRE = '/Game/Recovered/SourceStages/Maps/L_Theatre'
TUTORIAL = '/Game/Recovered/Battle/Maps/L_TutorialBattle'
TUTORIAL_ASSETS = '/Game/Recovered/Battle/BattleSceneAssets'
TARGET = '/Game/Recovered/Battle/Maps/L_PrologueBoss1703'
SCENE_ASSETS = '/Game/Recovered/Battle/PrologueBoss1703SceneAssets'
MECHANISMS = ROOT / 'analysis/prologue-boss/mechanism-audit/report.json'
MECHANISMS_SHA = '6fdb8945e1f197b24dc71746169078407b7c488d7884a36666617a67a97ba26f'
ENEMY_SKILLS = ROOT / 'analysis/prologue-boss/mechanism-audit/enemySkills.json'
ENEMY_SKILLS_SHA = '1be4dea9663cc97674efdc37e037f993d8cbc38d5d55e0aa6919339ebfe53d29'
BOSS_REPORT = ROOT / 'analysis/prologue-boss/glb/export-report.json'
BOSS_REPORT_SHA = '969e97367ce143841ed7748a46423586db35fdc0a18fb4181ce563b557418583'
FIXTURE = PROJECT / 'Source/Hczs/Private/Tests/Fixtures/prologue-boss-party-v1.json'
FUTURE_ACTIONS = ROOT / 'analysis/prologue-boss/future-actions/report.json'
FUTURE_ACTIONS_SHA = '239484e1e2202979bb49149a6dda8d26a2ec691fcfc2dbe9fbb484a29d0ec547'
FUTURE_EXPORT = ROOT / 'analysis/characters/hero-003/battle-actions/export/export-report.json'
CLIP_PREFIX = 'muoumaxituan_'
RUNTIME_VERTICAL_FOV = 35.985


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def vec(value):
    return [value.x, value.y, value.z]


def asset_file(path, world=False):
    return PROJECT / 'Content' / (path[6:].split('.')[0] + ('.umap' if world else '.uasset'))


def recipe():
    raw = MECHANISMS.read_bytes()
    check(sha(raw) == MECHANISMS_SHA, 'Boss mechanism audit changed')
    check(sha(BOSS_REPORT.read_bytes()) == BOSS_REPORT_SHA, 'Boss GLB export report changed')
    skills = {str(row['id']): row['animation'] for row in json.loads(raw)['skills']}
    check(skills == {'74501': CLIP_PREFIX + 'skill_4', '74502': CLIP_PREFIX + 'skill_3', '74503': CLIP_PREFIX + 'skill_2'},
          'Boss skill animation mapping changed')
    check(sha(ENEMY_SKILLS.read_bytes()) == ENEMY_SKILLS_SHA, 'Boss skill effect evidence changed')
    effects = {str(row['id']): row['fields']['SKILL_TARGET_SFX'] for row in json.loads(ENEMY_SKILLS.read_text('utf8'))['rows']}
    check(effects == {'74501': 'effects/boss/muoumaxitua/muoumaxituan_shouji_01.sfx',
                      '74502': 'effects/boss/muoumaxitua/muoumaxituan_shouji_01.sfx',
                      '74503': 'effects/boss/muoumaxitua/muoumaxituan_skill_2_03.sfx'}, 'Boss skill effect paths changed')
    scenario = json.loads(FIXTURE.read_text('utf8'))['initial']['battle']['scenario']
    definition = scenario['definition']
    check(scenario['encounterId'] == 'prologue-boss-1703' and definition['enemy']['id'] == '2013'
          and [m['id'] for m in definition['party']] == ['1', '3'], 'Boss party definition changed')
    elsa_cards = sorted({entry['cardId'] for entry in definition['deck'] if entry['ownerId'] == '1'})
    check(elsa_cards, 'Boss deck has no Elsa cards')
    actions_raw = FUTURE_ACTIONS.read_bytes()
    check(sha(actions_raw) == FUTURE_ACTIONS_SHA, 'Future action mapping changed')
    actions = json.loads(actions_raw)
    future_cards = sorted({entry['cardId'] for entry in definition['deck'] if entry['ownerId'] == '3'})
    check(sorted(actions['cardClips']) == future_cards and actions['memberIndex'] == 1, 'Future card mapping does not cover the boss deck')
    return dict(encounterId='prologue-boss-1703', playerId='party-1-3', enemyId='2013',
                enemySkillClips={key: value[len(CLIP_PREFIX):] for key, value in skills.items()},
                enemySkillEffects=effects,
                elsaCards=elsa_cards, sceneSha256=SCENE_SHA, mechanismsSha256=MECHANISMS_SHA,
                bossReportSha256=BOSS_REPORT_SHA, futureGlbSha256=actions['glbSha256'], futureClips=actions['clips'],
                futureCardClips=actions['cardClips'], futureActionsSha256=FUTURE_ACTIONS_SHA)


def main():
    plan = recipe()
    check('-HczsPrologueBossApply' in u.SystemLibrary.get_command_line().split(), 'Require -HczsPrologueBossApply in a dedicated Editor')
    check(u.SystemLibrary.get_engine_version().startswith('5.8.'), 'Wrong engine')
    check(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Retain unsaved editor maps before running this setup')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    protected = {}
    for path in (asset_file(THEATRE, True), asset_file(TUTORIAL, True), asset_file(TUTORIAL_ASSETS)):
        check(path.is_file(), 'Protected input absent: ' + str(path))
        protected[str(path)] = sha(path.read_bytes())

    def unique(tag):
        matches = [actor for actor in actors.get_all_level_actors() if actor.actor_has_tag(tag)]
        check(len(matches) == 1, 'Missing/duplicated actor tag: ' + tag)
        return matches[0]

    def load_map(path):
        world = u.EditorLoadingAndSavingUtils.load_map(path)
        check(world is not None and world.get_path_name().split('.')[0] == path, 'Cannot load exact map: ' + path)
        return world

    boss_mesh, boss_idle, _ = import_boss()
    future_mesh, future_sequences = import_future_glb(FUTURE_EXPORT, plan['futureGlbSha256'], 'battle-actions', len(plan['futureClips']))
    future_clips = {}
    for clip in plan['futureClips']:
        matches = [s for s in future_sequences if s.get_name() == future_mesh.get_name() + clip]
        check(len(matches) == 1, 'Future clip not uniquely imported: ' + clip)
        future_clips[clip] = matches[0]
    future_idle = future_clips['idle_1']
    position, rotation, camera_matrix, elsa_position, elsa_rotation, future_position, future_rotation = source_placement()
    boss_clips = {}
    for path in u.EditorAssetLibrary.list_assets(boss_idle.get_path_name().rsplit('/', 1)[0], True, False):
        asset = u.load_asset(path)
        if isinstance(asset, u.AnimSequence):
            name = asset.get_name()
            check(CLIP_PREFIX in name, 'Unexpected boss clip name: ' + name)
            boss_clips[name.split(CLIP_PREFIX, 1)[1]] = asset
    check(sorted(boss_clips) == ['death', 'hit_1', 'hit_2', 'idle', 'skill_2', 'skill_3', 'skill_4'], 'Boss clip set changed')

    load_map(TUTORIAL)
    player = unique('HCZSBattlePlayer').get_component_by_class(u.SkeletalMeshComponent)
    weapon = unique('HCZSBattleWeapon').get_component_by_class(u.StaticMeshComponent)
    template = dict(
        playerMesh=player.get_skeletal_mesh_asset(),
        playerMaterials=[player.get_material(i) for i in range(player.get_num_materials())],
        playerScale=unique('HCZSBattlePlayer').get_actor_scale3d(),
        weaponMesh=weapon.get_editor_property('static_mesh'),
        weaponMaterials=[weapon.get_material(i) for i in range(weapon.get_num_materials())],
        weaponSocket=str(weapon.get_attach_socket_name()), weaponRelative=weapon.get_relative_transform())
    check(template['weaponSocket'] == 'bip001-prop1', 'Template weapon socket changed')
    source_assets = u.load_asset(TUTORIAL_ASSETS)
    check(source_assets.get_editor_property('supported_encounter_id') == 'tutorial-5000'
          and source_assets.get_editor_property('player_mesh') == template['playerMesh'], 'Tutorial SceneAssets changed')

    if u.EditorAssetLibrary.does_asset_exist(SCENE_ASSETS):
        assets = u.load_asset(SCENE_ASSETS)
        check(isinstance(assets, u.HczsBattleSceneAssets), 'Owned SceneAssets path holds another asset type')
        for key in ('source_hit_timing_sha256', 'player_mesh', 'player_animations', 'player_hit_events'):
            assets.set_editor_property(key, source_assets.get_editor_property(key))
    else:
        assets = u.EditorAssetLibrary.duplicate_asset(TUTORIAL_ASSETS, SCENE_ASSETS)
    check(assets is not None, 'Cannot create owned SceneAssets')
    queues = source_assets.get_editor_property('card_animation_queues')
    card_queues = {card: queues[card] for card in plan['elsaCards'] if card in queues}
    for key, value in dict(
            supported_encounter_id=plan['encounterId'], player_id=plan['playerId'], enemy_id=plan['enemyId'],
            enemy_mesh=boss_mesh, enemy_animations=boss_clips, enemy_skill_clips=plan['enemySkillClips'],
            enemy_skill_effects=plan['enemySkillEffects'],
            card_animation_queues=card_queues, source_mapping_sha256=MECHANISMS_SHA,
            source_manifest_sha256=BOSS_REPORT_SHA, original_tutorial_stage_recovered=False,
            ally_mesh=future_mesh, ally_member_index=1, ally_animations=future_clips, ally_card_clips=plan['futureCardClips'],
            scene_notice='序章首领战：原剧场、首领与艾尔莎/未来模型、未来源战斗动作及首领技能动作；双人规则为重建，原特效/音效未接').items():
        assets.set_editor_property(key, value)
    check(u.EditorAssetLibrary.save_loaded_asset(assets, False), 'Boss SceneAssets save failed')

    if u.EditorAssetLibrary.does_asset_exist(TARGET):
        check(u.EditorAssetLibrary.delete_asset(TARGET), 'Cannot replace owned boss map')
    theatre = load_map(THEATRE)
    check(not any(str(tag).startswith('HCZSBattle') for actor in actors.get_all_level_actors() for tag in actor.get_editor_property('tags')),
          'Theatre already contains battle actors')
    check(u.EditorLoadingAndSavingUtils.save_map(theatre, TARGET), 'Cannot copy theatre into boss map')
    world = load_map(TARGET)

    def place(label, tags, mesh, idle, source_position, source_rotation):
        actor = actors.spawn_actor_from_class(u.SkeletalMeshActor, to_ue(source_position) * 100,
            u.MathLibrary.make_rot_from_xz(to_ue(source_rotation[8:11]), to_ue(source_rotation[4:7])))
        actor.set_actor_label(label)
        actor.set_editor_property('tags', tags)
        component = actor.get_component_by_class(u.SkeletalMeshComponent)
        component.set_skeletal_mesh_asset(mesh)
        component.override_animation_data(idle, True, True, 0., 1.)
        component.set_update_animation_in_editor(True)
        component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        return actor, component

    elsa_idle = source_assets.get_editor_property('player_animations')['idle_1']
    elsa, elsa_component = place('HCZSBattlePlayer', ['HCZSBattlePlayer'], template['playerMesh'], elsa_idle, elsa_position, elsa_rotation)
    elsa.set_actor_scale3d(template['playerScale'])
    for index, material in enumerate(template['playerMaterials']):
        elsa_component.set_material(index, material)
    place('HCZSBattleEnemy', ['HCZSBattleEnemy'], boss_mesh, boss_clips['idle'], position, rotation)
    place('HCZSBattleAlly3', ['HCZSBattleAlly', 'HCZSBattleAlly3'], future_mesh, future_idle, future_position, future_rotation)
    weapon_actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
    weapon_actor.set_actor_label('HCZSBattleWeapon')
    weapon_actor.set_editor_property('tags', ['HCZSBattleWeapon'])
    weapon_component = weapon_actor.get_component_by_class(u.StaticMeshComponent)
    weapon_component.set_mobility(u.ComponentMobility.MOVABLE)
    weapon_component.set_static_mesh(template['weaponMesh'])
    weapon_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    for index, material in enumerate(template['weaponMaterials']):
        weapon_component.set_material(index, material)
    check(elsa_component.get_bone_index(template['weaponSocket']) >= 0 and weapon_component.attach_to_component(
        elsa_component, template['weaponSocket'], u.AttachmentRule.KEEP_RELATIVE, u.AttachmentRule.KEEP_RELATIVE,
        u.AttachmentRule.KEEP_RELATIVE, False), 'Cannot attach weapon to Elsa')
    weapon_component.set_relative_transform(template['weaponRelative'], False, True)
    camera = actors.spawn_actor_from_class(u.CameraActor, to_ue(camera_matrix[12:15]) * 100,
        u.MathLibrary.make_rot_from_xz(to_ue(camera_matrix[8:11]), to_ue(camera_matrix[4:7])))
    camera.set_actor_label('HCZSBattleCamera')
    camera.set_editor_property('tags', ['HCZSBattleCamera'])
    camera.set_editor_property('auto_activate_for_player', u.AutoReceiveInput.PLAYER0)
    camera.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 45)
    presentation = actors.spawn_actor_from_class(u.load_class(None, '/Script/Hczs.HczsBattlePresentation'), u.Vector())
    presentation.set_actor_label('HCZSBattlePresentation')
    presentation.set_editor_property('tags', ['HCZSBattlePresentation'])
    presentation.set_editor_property('scene_assets', assets)
    mode = u.load_class(None, '/Script/Hczs.HczsBattleMode')
    check(mode is not None, 'Native battle mode missing')
    world.get_world_settings().set_editor_property('default_game_mode', mode)
    check(u.EditorLoadingAndSavingUtils.save_map(world, TARGET), 'Cannot save boss map')

    load_map(TARGET)
    assets = u.load_asset(SCENE_ASSETS)
    check(unique('HCZSBattlePresentation').get_editor_property('scene_assets') == assets, 'Presentation lost its SceneAssets')
    check(unique('HCZSBattlePlayer').get_component_by_class(u.SkeletalMeshComponent).get_skeletal_mesh_asset() == assets.get_editor_property('player_mesh'), 'Player mesh differs')
    check(unique('HCZSBattleEnemy').get_component_by_class(u.SkeletalMeshComponent).get_skeletal_mesh_asset() == boss_mesh, 'Boss mesh differs')
    check(dict(assets.get_editor_property('enemy_skill_clips')) == plan['enemySkillClips'], 'Skill clip readback differs')
    check(dict(assets.get_editor_property('enemy_skill_effects')) == plan['enemySkillEffects'], 'Skill effect readback differs')
    check(dict(assets.get_editor_property('ally_card_clips')) == plan['futureCardClips']
          and sorted(assets.get_editor_property('ally_animations')) == sorted(plan['futureClips'])
          and unique('HCZSBattleAlly3').get_component_by_class(u.SkeletalMeshComponent).get_skeletal_mesh_asset() == future_mesh,
          'Future action readback differs')
    cc = unique('HCZSBattleCamera').get_component_by_class(u.CameraComponent)
    from verify_battle_scene import project
    axes = dict(position=vec(cc.get_world_transform().translation), forward=vec(cc.get_forward_vector()),
                right=vec(cc.get_right_vector()), up=vec(cc.get_up_vector()),
                horizontal_fov=math.degrees(2 * math.atan(math.tan(math.radians(RUNTIME_VERTICAL_FOV) / 2) * 16 / 9)), aspect_ratio=16 / 9)
    projections = {tag: project(vec(unique(tag).get_actor_location()), axes)
                   for tag in ('HCZSBattlePlayer', 'HCZSBattleAlly3', 'HCZSBattleEnemy')}
    check(all(p['inside'] for p in projections.values()), 'Camera_1 does not frame all three combatants')
    check(all(Path(path).is_file() and sha(Path(path).read_bytes()) == digest for path, digest in protected.items()),
          'A protected source map/asset changed on disk')
    return dict(passed=True, map=TARGET, sceneAssets=SCENE_ASSETS, recipe=plan,
                cardQueues=sorted(card_queues), cardsWithoutClips=[c for c in plan['elsaCards'] if c not in card_queues],
                bossClips=sorted(boss_clips), futureClips=sorted(future_clips), futureCardClips=plan['futureCardClips'],
                projections=projections, protectedFilesUnchanged=True,
                mapSha256=sha(asset_file(TARGET, True).read_bytes()),
                limitations=['Elsa/Future/boss/camera use boss_theatre source placements; FOV follows HczsBattleCamera at runtime.',
                             'Future card clips follow skill timelines (SPL_1/SHD_UP_1); hit_1 on damage, death on defeat and show with the Elsa entrance are reconstructed timing.',
                             'Boss skill clips are source-mapped (74501/2/3); skill VFX, SFX and transform phases are not ported.',
                             'Two-member rules are prologue-party-reconstruction-v1, not observed original runtime.'])


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    started = int(time.time() * 1000)
    try:
        result = main()
    except Exception:
        result = dict(passed=False, error=traceback.format_exc())
        u.log_error(result['error'])
    result['startedAtUnixMs'] = started
    (OUT / 'setup-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), 'utf8')
    u.SystemLibrary.quit_editor()
