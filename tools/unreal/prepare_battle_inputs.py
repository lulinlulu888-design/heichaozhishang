"""Stage hash-verified APK-derived battle assets independently of legacy Cocos.

Ordinary offline reconstruction evidence. This does not execute the APK or UE.
The original tutorial stage city_battle_3 is absent; city_battle_1 is an explicit
alternative stage, not a recovered original tutorial environment.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from export_elsa_model import split_glb, pack_glb
from export_elsa_animation import accessor_array
from trace_first_encounter import literal_table
from verify_unreal_assets import glb_summary

OUT = ROOT / 'analysis/unreal/battle-inputs'
APK_SHA = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
PINS = {
    'stage': ('analysis/battle-visual/city-scenes/city_battle_1/scene.glb',
              '17911447bd9f474658a6783c5adde7429c3f9c5c7f5733ae33fdc785d147b3eb'),
    'player': ('analysis/battle-visual/actor-battle-idle/prologue-elsa.glb',
               'acc7bbaa00b66a60165ce56341021055b55f1f73ca4c6af154e63036ee789463'),
    'enemy': ('analysis/battle-visual/enemy-reactions/enemy-reactions.glb',
              '4c43f8c85cb40a7ff6ecdad018aa341cfe3ef873606c23526cfcbd3eb3cc91b3'),
    'weapon': ('analysis/battle-visual/weapon/elsa-weapon-static.glb',
               '17e9dc3b061ead7aa333215f22920aef706f4403e44f32765cf476302fa7babe'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads((ROOT / path).read_text('utf8'))


def checked_source(path, expected):
    original = (ROOT / path).resolve()
    if not original.is_relative_to(ROOT.resolve()):
        raise ValueError('Input outside workspace')
    payload = original.read_bytes()
    if sha(payload) != expected:
        raise ValueError('Source identity mismatch: ' + path)
    return payload


def weapon_local_glb(blob, binding):
    """Preserve rigid source surface, bake source inverse bind into local verts.

    This is a labelled reconstruction attachment. The failed native bone AABB
    remains failed; this algebraic check does not establish BindType 263 semantics.
    """
    import numpy as np
    if not binding['all_vertices_single_joint_unit_weight'] or len(binding['used_bones']) != 1:
        raise ValueError('Rigid weapon source condition changed')
    bone = binding['used_bones'][0]
    if bone['name'] != 'bip001 prop1' or binding['bind_validation']['validated']:
        raise ValueError('Unexpected weapon source or changed unresolved status')
    matrix = np.asarray(bone['source_bind'], dtype=np.float64).reshape(4, 4).T
    inverse = np.linalg.inv(matrix)
    doc, binary = split_glb(blob)
    changed = []
    for primitive in doc['meshes'][0]['primitives']:
        index = primitive['attributes']['POSITION']
        old = accessor_array(doc, binary, index).astype(np.float64)
        homogeneous = np.column_stack((old, np.ones(len(old))))
        local = (inverse @ homogeneous.T).T[:, :3].astype('<f4')
        back = (matrix @ np.column_stack((local.astype(np.float64), np.ones(len(local)))).T).T[:, :3]
        error = float(np.max(np.abs(back - old)))
        if error > 2e-6:
            raise ValueError('Weapon local transform roundtrip failed')
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        binary[start:start + local.nbytes] = local.tobytes()
        accessor['min'], accessor['max'] = local.min(axis=0).tolist(), local.max(axis=0).tolist()
        normal_error = None
        if 'NORMAL' in primitive['attributes']:
            normal_index = primitive['attributes']['NORMAL']
            normals = accessor_array(doc, binary, normal_index).astype(np.float64)
            normal_matrix = np.linalg.inv(inverse[:3, :3]).T
            local_normals = (normal_matrix @ normals.T).T
            lengths = np.linalg.norm(local_normals, axis=1)
            if not np.all(np.isfinite(lengths)) or np.any(lengths < 1e-8):
                raise ValueError('Weapon normal cannot be transformed')
            local_normals = (local_normals / lengths[:, None]).astype('<f4')
            back_normals = (np.linalg.inv(matrix[:3, :3]).T @ local_normals.astype(np.float64).T).T
            back_normals /= np.linalg.norm(back_normals, axis=1)[:, None]
            original_unit = normals / np.linalg.norm(normals, axis=1)[:, None]
            normal_error = float(np.max(np.abs(back_normals - original_unit)))
            if normal_error > 2e-6:
                raise ValueError('Weapon normal roundtrip failed')
            normal_accessor = doc['accessors'][normal_index]
            normal_view = doc['bufferViews'][normal_accessor['bufferView']]
            normal_start = normal_view.get('byteOffset', 0) + normal_accessor.get('byteOffset', 0)
            binary[normal_start:normal_start + local_normals.nbytes] = local_normals.tobytes()
        changed.append(dict(accessor=index, vertices=len(old), roundtrip_max_error=error,
                            unit_normal_roundtrip_max_error=normal_error))
    doc['meshes'][0]['name'] = 'ElsaWeaponProp1Local'
    for node in doc['nodes']:
        if 'mesh' in node:
            node['name'] = 'ElsaWeaponProp1Local'
    doc.setdefault('extras', {})['reconstructionAttachment'] = dict(
        source_glb_sha256=sha(blob), source_bind=bone['source_bind'],
        source_bone='bip001 prop1', ue_bone='bip001-prop1', native_bind_type=263,
        native_bind_semantics_verified=False, native_bone_aabb_verified=False,
        policy='source prop1 animation matrix multiplied by original weapon inverse bind',
        numerical_roundtrip=changed)
    return pack_glb(doc, binary), doc['extras']['reconstructionAttachment']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA:
            raise ValueError('Original APK changed')
    blobs = {key: checked_source(*value) for key, value in PINS.items()}
    stage_report = read_json('analysis/battle-visual/city-scenes/city_battle_1/export.json')
    dependencies = {row['path']: row for row in read_json('analysis/battle-visual/city-scenes/dependencies.json')['records']}
    for source in stage_report['sources']:
        row = dependencies[source['path']]
        if row['status'] != 'present' or row['sha256'] != source['sha256']:
            raise ValueError('Stage dependency provenance changed')
        checked_source(row['localPath'], source['sha256'])
    player_report = read_json('analysis/battle-visual/actor-battle-idle/report.json')
    enemy_report = read_json('analysis/battle-visual/enemy-reactions/report.json')
    if player_report['glb_sha256'] != PINS['player'][1] or enemy_report['glb_sha256'] != PINS['enemy'][1]:
        raise ValueError('Animation export report identity changed')
    for source_kind, digest in player_report['source_hashes'].items():
        checked_source('analysis/battle-visual/scene-export/source/File_26.' + source_kind, digest)
    for is_player, report in ((True, player_report), (False, enemy_report)):
        for clip in report['clips']:
            source = clip['source']
            if source['apk_sha256'] != APK_SHA:
                raise ValueError('Clip belongs to another APK')
            name = clip['name']
            folder = ('analysis/animation/recovered' if name == 'stand_idle' else
                      'analysis/battle-visual/battle-idle' if name == 'idle_1' else
                      'analysis/battle-visual/player-reactions' if name in ('hit_2', 'death') else
                      'analysis/battle-visual/skill-animation') if is_player else (
                      'analysis/tutorial-enemy-animation' if name in ('idle', 'fire') else
                      'analysis/battle-visual/enemy-reactions' if name in ('hit_1', 'death') else
                      'analysis/battle-visual/enemy-skills')
            checked_source(folder + '/' + name + '.gisacl', source['sha256'])
            checked_source(folder + '/' + name + '.poses', clip['pose_sha256'])
    tables = literal_table(1955, {0, 6605})
    entities = {row['id']: row['fields'] for row in tables['rows']}
    if entities[0]['ANIM_STATES_IDLE_1'] != 'idle_1' or entities[6605]['ANIM_STATES_IDLE_1'] != 'idle':
        raise ValueError('Source normal battle idle mapping changed')
    scene_doc, scene_bin = split_glb(blobs['stage'])
    scene_doc = copy.deepcopy(scene_doc)
    name_changes = []
    for index, node in enumerate(scene_doc['nodes']):
        original_name = node['name']
        node['name'] = 'BattleStage_%03d' % index
        node.setdefault('extras', {})['sourceNodeName'] = original_name
        name_changes.append(dict(index=index, source_name=original_name, name=node['name']))
    stage = pack_glb(scene_doc, scene_bin)
    # Only discard the out-of-battle inspection clip, retaining all geometry,
    # inverse binds, original images and animation sample bytes unchanged.
    player_doc, player_bin = split_glb(blobs['player'])
    player_doc['animations'] = [a for a in player_doc['animations'] if a['name'] != 'stand_idle']
    player_clips = [a['name'] for a in player_doc['animations']]
    if player_clips != ['fire_1', 'crit_1', 'fire_1_1', 'fire_1_3', 'fire_2', 'hit_2', 'death', 'idle_1']:
        raise ValueError('Battle clip selection changed')
    player_doc['extras']['scenePlaybackScope'] = 'Source Elsa battle idle_1, five attacks, hit_2 and death. No hall/stand idle selected.'
    player = pack_glb(player_doc, player_bin)
    weapon_binding = read_json('analysis/battle-visual/weapon/binding-report.json')
    weapon, attachment = weapon_local_glb(blobs['weapon'], weapon_binding)
    rows = []
    for identifier, payload, target, operation in (
        ('stage', stage, 'stage/city_battle_1.glb', 'scene'),
        ('player', player, 'player/elsa_battle.glb', 'asset'),
        ('enemy', blobs['enemy'], 'enemy/cube_battle.glb', 'asset'),
        ('weapon', weapon, 'weapon/elsa_weapon.glb', 'asset')):
        path = OUT / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        doc, _ = split_glb(payload)
        rows.append(dict(id=identifier, file=target, sha256=sha(payload), bytes=len(payload),
                         source_file=PINS[identifier][0], source_sha256=PINS[identifier][1],
                         import_path='/Game/Recovered/Battle/' + {'stage':'Stage', 'player':'Elsa', 'enemy':'Cube', 'weapon':'Weapon'}[identifier],
                         import_operation=operation, geometry=glb_summary(doc)))
    source_camera = next(camera for camera in scene_doc['extras']['sourceCameras'] if camera['Name'] == 'camera_1')
    source_player = next(actor for actor in scene_doc['extras']['sourceActorInstances']
                         if actor['sourceInstance']['Name'] == '1' and actor['path'] == 'character/player/ailisha/ailisha.gim')
    # The alternative stage supplies source positions only for its own editor
    # actors. Use Elsa's original stage instance; cube is a deliberate replacement
    # at one opposing source editor slot, not tutorial spawn recovery.
    source_enemy = next(actor for actor in scene_doc['extras']['sourceActorInstances']
                        if actor['sourceInstance']['Name'] == 'duci_1215')
    player_position = source_player['matrix'][12:15]
    enemy_position = source_enemy['matrix'][12:15]
    layout = dict(
        encounter_id='tutorial-5000', source_tutorial_scene_id=2081,
        source_tutorial_scene_path='scene/city_battle_3/city_battle_3.scn',
        alternative_stage='scene/city_battle_1/city_battle_1.scn', original_tutorial_stage_recovered=False,
        source_camera=source_camera, source_player_instance=source_player, source_enemy_slot=source_enemy,
        player=dict(character_id=1, entity_id=0, normal_idle='idle_1', position=player_position,
                    rotation_radians=entities[0]['ROTATION'], scale=entities[0]['SCALE']),
        enemy=dict(monster_id=991, entity_id=6605, normal_idle='idle', position=enemy_position,
                   rotation_radians=[0, -math.pi/2, 0], scale=entities[6605]['SCALE'],
                   placement_policy='reconstruction replacement at city source opposing editor slot; facing toward Elsa'),
        camera=dict(primary_tag='HCZSBattleCamera', aspect_ratio=16/9,
                    inspection_position=[0, 0, 8], inspection_target=[0, -2, -56], vertical_fov=34,
                    source_projection_runtime_verified=False,
                    policy='source camera direction; inspection position/target/FOV for readable 1v1, full source camera preserved separately'),
        coordinates=dict(interchange_axis='source (x,y,z) -> UE (100x,100z,100y)',
                         after_import_world_reflection=[-1, 1, 1],
                         reflection_reason='native source camera horizontal basis -X and forward -Z; left-side positive source X',
                         additional_global_yaw_degrees=0, physical_unit_factor_verified=False),
        actor_tags=dict(player='HCZSBattlePlayer', enemy='HCZSBattleEnemy', weapon='HCZSBattleWeapon'),
        source_entity_table=tables, weapon_attachment=attachment)
    (OUT/'layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    manifest = dict(schema='hczs-unreal-battle-inputs-v1', source_apk_sha256=APK_SHA, assets=rows,
                    layout_file='layout.json', layout_sha256=sha((OUT/'layout.json').read_bytes()),
                    map='/Game/Recovered/Battle/Maps/L_TutorialBattle',
                    transformations=dict(stage_node_name_changes=name_changes,
                        stage_binary_preserved=True, player_binary_preserved=True, enemy_bytes_preserved=True,
                        removed_player_clip='stand_idle', weapon_source_inverse_bind_baked_to_local_vertices=True),
                    evidence_kind='Ordinary hash-verified offline extraction/conversion, not new REA Evidence or original runtime',
                    limitations=['city_battle_3 tutorial environment is absent; city_battle_1 is a marked alternative stage.',
                        'Single hero/cube reconstruction; original team, enemy spawning and camera sequencing not restored.',
                        'Colour reference only; original lighting, toon, emission, cloud shader, particles and attack VFX not restored.',
                        'Rigid weapon attachment is reconstruction; native BindType 263 and weapon bone-AABB discrepancy unresolved.',
                        'Animations are source samples; runtime event scheduling, interpolation and skill effects remain separate.',
                        'UE import, visible rendering and playable network loop must be verified separately.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    print(json.dumps(dict(manifest=str(OUT/'manifest.json'), assets=len(rows), player_clips=player_clips,
                         stage_meshes=rows[0]['geometry']['meshes'], stage_instances=rows[0]['geometry']['mesh_instances'])))


if __name__ == '__main__':
    main()
