"""Reuse verified source material overrides and weapon attachment in city2077.

Only the independent city map is saved. Capture the real editor camera after
render warmup; no business battle or original-camera fidelity is asserted.
"""
import json
import hashlib
from pathlib import Path
import sys
import time
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from export_elsa_model import split_glb
BASE = ROOT / 'analysis/unreal/city-preview'
CITY = '/Game/Recovered/City/Maps/L_City2077Preview'
TUTORIAL = '/Game/Recovered/Battle/Maps/L_TutorialBattle'
REPORT = BASE / 'visual-result.json'
HIDE_ENEMY = '-HczsCityHideEnemy' in u.SystemLibrary.get_command_line()
HIDE_CLOUD = '-HczsCityHideCloud' in u.SystemLibrary.get_command_line()
ATLAS_NO_MIPS = '-HczsCityAtlasNoMips' in u.SystemLibrary.get_command_line()
SHOT = BASE / ('city2077-atlas.png' if ATLAS_NO_MIPS else 'city2077-no-cloud.png' if HIDE_CLOUD else 'city2077-no-enemy.png' if HIDE_ENEMY else 'city2077-framed.png')


def setup():
    if SHOT.exists():
        raise RuntimeError('Retain existing capture; choose a fresh capture path before retry')
    # Reuse cloud shader only when original material parameters are identical.
    mats = []
    for name in ('city_battle_1', 'city_battle_2'):
        doc, _ = split_glb((ROOT / f'analysis/battle-visual/city-scenes/{name}/scene.glb').read_bytes())
        candidates = [m for m in doc['materials'] if m.get('extras', {}).get('sourceModel') == 'effects/modeleffect/scene/plane_yun.gim']
        if len(candidates) != 1:
            raise RuntimeError('Source cloud material ambiguous')
        mats.append(candidates[0]['extras'])
    if mats[0]['sourceMaterialXML'] != mats[1]['sourceMaterialXML'] or mats[0]['sourceParams'] != mats[1]['sourceParams']:
        raise RuntimeError('City cloud differs from verified source material')
    original = ROOT / 'clients/unreal5 5.8/Content/Recovered/Battle/Maps/L_TutorialBattle.umap'
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    subsystem = u.get_editor_subsystem(u.EditorActorSubsystem)
    u.EditorLoadingAndSavingUtils.load_map(TUTORIAL)
    actors = list(subsystem.get_all_level_actors())
    refs = {}
    for side, tag, cls in [('player', 'HCZSBattlePlayer', u.SkeletalMeshComponent), ('enemy', 'HCZSBattleEnemy', u.SkeletalMeshComponent), ('weapon', 'HCZSBattleWeapon', u.StaticMeshComponent)]:
        matches = [a for a in actors if a.actor_has_tag(tag)]
        if len(matches) != 1:
            raise RuntimeError('Missing source actor ' + tag)
        c = matches[0].get_component_by_class(cls)
        refs[side] = dict(materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())])
        if side == 'weapon':
            refs[side].update(mesh=c.get_editor_property('static_mesh').get_path_name(), bone=str(c.get_attach_socket_name()))
    cloud_paths = {c.get_material(0).get_path_name() for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)
                   if c.get_material(0) and c.get_material(0).get_name() == 'M_OriginalCloudMaskedFlow'}
    if len(cloud_paths) != 1:
        raise RuntimeError('Verified cloud override missing')
    world = u.EditorLoadingAndSavingUtils.load_map(CITY)
    actors = list(subsystem.get_all_level_actors())
    components = {}
    for side in ('player', 'enemy'):
        actor = next(a for a in actors if a.get_actor_label() == 'City2077_' + side)
        c = actor.get_component_by_class(u.SkeletalMeshComponent)
        if c.get_num_materials() != len(refs[side]['materials']):
            raise RuntimeError('Actor material slot count differs')
        for i, path in enumerate(refs[side]['materials']):
            c.set_material(i, u.load_asset(path))
        components[side] = c
    weapons = [a for a in actors if a.get_actor_label() == 'City2077_weapon']
    if len(weapons) > 1:
        raise RuntimeError('Duplicate city weapon')
    weapon = weapons[0] if weapons else subsystem.spawn_actor_from_class(u.StaticMeshActor, u.Vector(0, 0, 0))
    weapon.set_actor_label('City2077_weapon')
    wc = weapon.get_component_by_class(u.StaticMeshComponent)
    wc.set_mobility(u.ComponentMobility.MOVABLE)
    wc.set_static_mesh(u.load_asset(refs['weapon']['mesh']))
    wc.set_editor_property('cast_shadow', False)
    for i, path in enumerate(refs['weapon']['materials']):
        wc.set_material(i, u.load_asset(path))
    bone = refs['weapon']['bone']
    if components['player'].get_bone_index(bone) < 0 or not wc.attach_to_component(components['player'], bone,
        u.AttachmentRule.SNAP_TO_TARGET, u.AttachmentRule.SNAP_TO_TARGET, u.AttachmentRule.SNAP_TO_TARGET, False):
        raise RuntimeError('Weapon attachment failed')
    clouds = []
    for actor in actors:
        for c in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = c.get_editor_property('static_mesh')
            if mesh and 'plane_yun' in mesh.get_name().lower():
                c.set_material(0, u.load_asset(next(iter(cloud_paths))))
                clouds.append(actor.get_path_name())
    if len(clouds) != 1:
        raise RuntimeError('Expected exactly one city source cloud surface: ' + str(clouds))
    if ATLAS_NO_MIPS:
        atlas_components = [c for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)
            if c.get_editor_property('static_mesh') and 'city_battle_02_fg_01' in c.get_editor_property('static_mesh').get_name()]
        if len(atlas_components) != 1 or atlas_components[0].get_num_materials() != 2:
            raise RuntimeError('Unexpected original atlas surface inventory')
        for slot in range(2):
            original_material = atlas_components[0].get_material(slot)
            texture = u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(original_material, 'BaseColorTexture')
            if not texture:
                raise RuntimeError('Original atlas texture missing')
            dest = '/Game/Recovered/City/AtlasNoMips/'
            tex_path = dest + 'T_Background'
            derived = u.load_asset(tex_path) if u.EditorAssetLibrary.does_asset_exist(tex_path) else u.EditorAssetLibrary.duplicate_asset(texture.get_path_name(), tex_path)
            derived.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            derived.set_editor_property('filter', u.TextureFilter.TF_BILINEAR)
            derived.set_editor_property('never_stream', True)
            u.EditorAssetLibrary.save_loaded_asset(derived, False)
            material_path = dest + 'MI_Background_' + str(slot)
            material = u.load_asset(material_path) if u.EditorAssetLibrary.does_asset_exist(material_path) else u.EditorAssetLibrary.duplicate_asset(original_material.get_path_name(), material_path)
            u.MaterialEditingLibrary.set_material_instance_texture_parameter_value(material, 'BaseColorTexture', derived)
            u.EditorAssetLibrary.save_loaded_asset(material, False)
            atlas_components[0].set_material(slot, material)
    camera = next(a for a in actors if a.get_actor_label() == 'City2077_InspectionCamera')
    location, target = u.Vector(400, 800, 0), u.Vector(400, -4500, -650)
    camera.set_actor_location(location, False, False)
    camera.set_actor_rotation(u.MathLibrary.find_look_at_rotation(location, target), False)
    camera.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 70.0)
    if not u.EditorLoadingAndSavingUtils.save_map(world, CITY):
        raise RuntimeError('City map save failed')
    if hashlib.sha256(original.read_bytes()).hexdigest() != before:
        raise RuntimeError('Tutorial map changed')
    if HIDE_ENEMY:
        # Diagnostic visibility only, after saving: never persist this in the map.
        components['enemy'].set_visibility(False, True)
    if HIDE_CLOUD:
        for actor in actors:
            if actor.get_path_name() in clouds:
                actor.get_component_by_class(u.StaticMeshComponent).set_visibility(False, True)
    camera = next(a for a in actors if a.get_actor_label() == 'City2077_InspectionCamera')
    return camera, dict(passed=True, materialBindings=refs, cloudActors=clouds, tutorialMapUnchanged=True,
                        nativeWeaponSemanticsVerified=False, originalLightingRestored=False,
                        enemyHiddenForDiagnosis=HIDE_ENEMY, cloudHiddenForDiagnosis=HIDE_CLOUD,
                        atlasNoMipsAdapter=ATLAS_NO_MIPS, screenshot=str(SHOT))


def tick(delta):
    global task, handle
    try:
        if time.monotonic() - started > 60:
            raise RuntimeError('Native screenshot deadline exceeded')
        if task is None and time.monotonic() - started > 5:
            task = u.AutomationLibrary.take_high_res_screenshot(1600, 900, str(SHOT), camera=camera, delay=1.0)
        elif task is not None and task.is_task_done():
            if not SHOT.exists():
                raise RuntimeError('Screenshot task completed without image')
            result['screenshotBytes'] = SHOT.stat().st_size
            REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), 'utf8')
            u.unregister_slate_post_tick_callback(handle)
            u.SystemLibrary.quit_editor()
    except Exception:
        REPORT.write_text(json.dumps(dict(passed=False, error=traceback.format_exc()), indent=2), 'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


try:
    camera, result = setup()
    started, task = time.monotonic(), None
    handle = u.register_slate_post_tick_callback(tick)
except Exception:
    REPORT.write_text(json.dumps(dict(passed=False, error=traceback.format_exc()), indent=2), 'utf8')
    u.SystemLibrary.quit_editor()
