"""Read-only Elsa pose comparison: pinned ACL -> GLB -> UE AnimPose.

Ordinary Python computes source matrices. Unreal Python reads loaded asset pose
data and a separately loaded saved preview map; no asset/map save or live editor
operation is performed. Set HCZS_UE_POSE_CAPTURE=1 for Unreal capture mode.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/unreal/pose'
KEY_BONES = ('bip001', 'bip001 pelvis', 'bip001 spine', 'bip001 spine1',
             'bip001 neck', 'bip001 head', 'bip001 l foot', 'bip001 r foot')
TIMES = (0., 1., 2., 3., 4.)
SUFFIX = os.environ.get('HCZS_UE_POSE_SUFFIX', '')
if SUFFIX not in ('', '-after'):
    raise ValueError('Unsupported pose report suffix')
CAPTURE_NAME = 'ue-capture' + SUFFIX + '.json'
MAP_PATH = os.environ.get('HCZS_UE_POSE_MAP', '/Game/Recovered/Hall/Maps/L_ElsaHallPreview')
if MAP_PATH not in ('/Game/Recovered/Hall/Maps/L_ElsaHallPreview', '/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview'):
    raise ValueError('Unapproved pose readback map')


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')


def transform_row(transform):
    t = transform.translation
    q = transform.rotation
    s = transform.scale3d
    return dict(translation=[t.x, t.y, t.z], rotation=[q.x, q.y, q.z, q.w], scale=[s.x, s.y, s.z])


def capture_unreal():
    import unreal
    result = dict(schema='hczs-ue-elsa-pose-capture-v1', engine_version=unreal.SystemLibrary.get_engine_version(),
                  read_only=True, samples=[], actors=[], errors=[], api_docs={})
    probe = unreal.Rotator(0, -20, 0)
    result['rotator_constructor_probe'] = dict(arguments=[0,-20,0], pitch=probe.pitch, yaw=probe.yaw, roll=probe.roll,
                                               class_doc=unreal.Rotator.__doc__)
    result['map'] = MAP_PATH
    write(CAPTURE_NAME, result)
    try:
        mesh = unreal.load_asset('/Game/Recovered/Elsa/elsa')
        animation = unreal.load_asset('/Game/Recovered/Elsa/elsa_Anim')
        if not mesh or not animation:
            raise RuntimeError('Elsa imported mesh/animation missing')
        result['mesh'] = mesh.get_path_name()
        result['animation'] = animation.get_path_name()
        result['duration'] = animation.get_play_length()
        result['api_docs']['get_anim_pose_at_time'] = unreal.AnimPoseExtensions.get_anim_pose_at_time.__doc__
        for evaluation, retarget in (('SOURCE', False), ('RAW', False), ('COMPRESSED', False), ('COMPRESSED', True)):
            options = unreal.AnimPoseEvaluationOptions()
            options.set_editor_property('evaluation_type', getattr(unreal.AnimDataEvalType, evaluation))
            options.set_editor_property('should_retarget', retarget)
            options.set_editor_property('extract_root_motion', False)
            options.set_editor_property('incorporate_root_motion_into_pose', True)
            options.set_editor_property('optional_skeletal_mesh', mesh)
            for time in TIMES:
                pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(animation, time, options)
                if not unreal.AnimPoseExtensions.is_valid(pose):
                    raise RuntimeError('UE AnimPose is invalid')
                names = {str(name) for name in unreal.AnimPoseExtensions.get_bone_names(pose)}
                row = dict(time_seconds=time, evaluation=evaluation, retarget=retarget,
                           available_bone_count=len(names), bones={})
                for original in KEY_BONES:
                    name = original.replace(' ', '-')
                    if name not in names:
                        raise RuntimeError('Missing corresponding UE bone: ' + name)
                    row['bones'][original] = dict(ue_name=name,
                        local=transform_row(unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.LOCAL)),
                        component=transform_row(unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.WORLD)),
                        reference_component=transform_row(unreal.AnimPoseExtensions.get_ref_bone_pose(pose, name, unreal.AnimPoseSpaces.WORLD)))
                result['samples'].append(row)
                write(CAPTURE_NAME, result)
        # Only this commandlet's separate world is loaded, and nothing is saved.
        world = unreal.EditorLoadingAndSavingUtils.load_map(MAP_PATH)
        if not world:
            raise RuntimeError('Saved Elsa preview map could not be loaded for readback')
        for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
            if not actor.get_actor_label().startswith('HCZS'):
                continue
            r = actor.get_actor_rotation()
            parent = actor.get_attach_parent_actor()
            row = dict(label=actor.get_actor_label(), actor_transform=transform_row(actor.get_actor_transform()),
                       actor_rotation=dict(pitch=r.pitch, yaw=r.yaw, roll=r.roll),
                       parent=parent.get_actor_label() if parent else None)
            component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            if component:
                row['component_transform'] = transform_row(component.get_world_transform())
            result['actors'].append(row)
        result['passed'] = True
    except Exception:
        result['passed'] = False
        result['errors'].append(traceback.format_exc())
        write(CAPTURE_NAME, result)
        raise
    write(CAPTURE_NAME, result)
    unreal.log('HCZS read-only Elsa pose capture: ' + str(OUT / CAPTURE_NAME))


def source_audit():
    import numpy as np
    sys.path.insert(0, str(ROOT / 'tools'))
    from export_elsa_animation import accessor_array, quaternion_matrix
    from export_elsa_model import split_glb
    from inspect_neox_model import parse_model, matrix_rows
    from inspect_neox_animation import parse_library
    source = ROOT / 'analysis/elsa-hall'
    meta = json.loads((source / 'home_stand_idle_1.json').read_text('utf8'))
    report = json.loads((source / 'export-report.json').read_text('utf8'))
    pose_bytes = (source / 'home_stand_idle_1.poses').read_bytes()
    if hashlib.sha256(pose_bytes).hexdigest() != meta['poses']['sha256']:
        raise ValueError('Pinned sampled ACL poses changed')
    glb_bytes = (source / 'elsa-hall-idle.colour-reference.glb').read_bytes()
    if hashlib.sha256(glb_bytes).hexdigest() != report['sha256']:
        raise ValueError('Pinned Elsa GLB changed')
    doc, binary = split_glb(glb_bytes)
    if doc['animations'][0]['name'] != 'home_stand_idle_1':
        raise ValueError('Wrong GLB clip')
    values = np.frombuffer(pose_bytes, dtype='<f4', offset=20).reshape(meta['samples'], meta['bone_count'], 10)
    mapping = {r['name']: r['clip_index'] for r in meta['bone_mapping']}
    mesh_bytes = Path(report['source_model']['mesh']['sample_path']).read_bytes()
    library_bytes = (source / 'ailisha.gisacl').read_bytes()
    if hashlib.sha256(mesh_bytes).hexdigest() != report['source_model']['mesh']['sha256'] or hashlib.sha256(library_bytes).hexdigest() != report['source_library']['sha256']:
        raise ValueError('Pinned original mesh/library changed')
    model = parse_model(mesh_bytes)
    library = parse_library(library_bytes)
    parents = {child: i for i, node in enumerate(doc['nodes']) for child in node.get('children', [])}
    joints = doc['skins'][0]['joints']
    by_name = {doc['nodes'][node]['name']: node for node in joints}
    glb_channels = {}
    for channel in doc['animations'][0]['channels']:
        sampler = doc['animations'][0]['samplers'][channel['sampler']]
        glb_channels[(channel['target']['node'], channel['target']['path'])] = accessor_array(doc, binary, sampler['output'])

    def matrix(p):
        mat = np.eye(4)
        mat[:3, :3] = quaternion_matrix(p[:4]) * p[7:10]
        mat[:3, 3] = p[4:7]
        return mat

    def worlds(local, model_parents):
        cache = {}
        def get(i):
            if i not in cache:
                parent = model_parents.get(i)
                cache[i] = get(parent) @ local[i] if parent is not None else local[i]
            return cache[i]
        return {i: get(i) for i in local}

    source_parents = {i: b['parent'] for i, b in enumerate(model['bones'])}
    model_names = [b['name'] for b in model['bones']]
    reference = dict(zip(library['bone_names'], library['reference_pose']))
    source_ref = worlds({i: matrix(np.r_[reference[name][3:7], reference[name][:3], reference[name][7:]])
                         for i, name in enumerate(model_names)}, source_parents)
    meshes = {b['name']: np.asarray(matrix_rows(b['matrix_raw'])) for b in model['bones']}
    source_ref_by_name = {name: source_ref[i] for i, name in enumerate(model_names)}
    ref_errors = {name: float(np.max(np.abs(source_ref_by_name[name] - meshes[name]))) for name in model_names}
    bad_ref = [{'name': name, 'max_matrix_error': error} for name, error in ref_errors.items() if error >= 1e-4]
    axis = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=float)
    preview = json.loads((ROOT / 'analysis/unreal/plan/hall-elsa-preview.json').read_text('utf8'))
    marker = preview['source_marker_matrix']
    yaw = math.atan2(marker[2], marker[0])
    rotation = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    reflect = np.diag([1, -1, 1])
    pitch, camera_yaw, roll = map(math.radians, preview['camera']['rotation'])
    right = np.array([-math.sin(camera_yaw), math.cos(camera_yaw), 0])
    up = np.array([-math.sin(pitch)*math.cos(camera_yaw), -math.sin(pitch)*math.sin(camera_yaw), math.cos(pitch)])

    def lean(points):
        foot = (points['bip001 l foot'] + points['bip001 r foot']) / 2
        head = points['bip001 head']
        torso = head - points['bip001 pelvis']
        body = head - foot
        projected_body = reflect @ rotation @ axis @ body
        return dict(foot_to_head_side_degrees=float(np.degrees(np.arctan2(body[0], body[1]))),
                    foot_to_head_depth_degrees=float(np.degrees(np.arctan2(body[2], body[1]))),
                    pelvis_to_head_side_degrees=float(np.degrees(np.arctan2(torso[0], torso[1]))),
                    pelvis_to_head_depth_degrees=float(np.degrees(np.arctan2(torso[2], torso[1]))),
                    source_projected_body_degrees=float(np.degrees(np.arctan2(right @ projected_body, up @ projected_body))))

    result = dict(schema='hczs-elsa-pose-audit-v1', evidence_kind='Original decoded APK numeric samples and local UE readback; no new REA Evidence ID',
                  source_clip_sha256=meta['source']['sha256'], source_pose_sha256=meta['poses']['sha256'],
                  known_source_reference_differences=bad_ref, samples=[], comparison=[],
                  validation=dict(glb_vs_acl_compared=True, unreal_readback_compared=False, original_native_renderer_observed=False))
    for time in TIMES:
        frame = int(round(time * meta['sample_rate']))
        acl_world = worlds({i: matrix(values[frame, mapping[name]]) for i, name in enumerate(model_names)}, source_parents)
        local_glb = {}
        for i, node in enumerate(doc['nodes']):
            if i in joints:
                local_glb[i] = matrix(np.r_[glb_channels[(i, 'rotation')][frame], glb_channels[(i, 'translation')][frame], glb_channels[(i, 'scale')][frame]])
            elif 'matrix' in node:
                local_glb[i] = np.asarray(node['matrix']).reshape(4, 4).T
            else:
                local_glb[i] = np.eye(4)
        glb_world = worlds(local_glb, parents)
        points = {name: acl_world[model_names.index(name)][:3, 3] for name in KEY_BONES}
        item = dict(time_seconds=time, frame=frame, source_lean=lean(points), bones={})
        for name in KEY_BONES:
            source_pose = values[frame, mapping[name]].astype(float)
            glb_matrix = glb_world[by_name[name]]
            original_matrix = acl_world[model_names.index(name)]
            item['bones'][name] = dict(source_local=dict(rotation=source_pose[:4].tolist(), translation=source_pose[4:7].tolist(), scale=source_pose[7:10].tolist()),
                                      source_component_translation=original_matrix[:3, 3].tolist(),
                                      glb_component_translation=glb_matrix[:3, 3].tolist(),
                                      glb_vs_acl_matrix_error=float(np.max(np.abs(glb_matrix - original_matrix))))
        result['samples'].append(item)
    capture_path = OUT / CAPTURE_NAME
    if capture_path.exists():
        capture = json.loads(capture_path.read_text('utf8'))
        for observed in capture['samples']:
            source_sample = next(s for s in result['samples'] if s['time_seconds'] == observed['time_seconds'])
            comparison = dict(time_seconds=observed['time_seconds'], evaluation=observed['evaluation'], retarget=observed['retarget'], bones={})
            for name in KEY_BONES:
                src = source_sample['bones'][name]
                ue = observed['bones'][name]
                expected_position = axis @ np.array(src['source_component_translation']) * 100
                actual_position = np.array(ue['component']['translation'])
                q = np.array(src['source_local']['rotation'])
                expected_q = np.array([-q[0], -q[2], -q[1], q[3]])
                actual_q = np.array(ue['local']['rotation'])
                dot = float(abs(expected_q @ actual_q) / (np.linalg.norm(expected_q) * np.linalg.norm(actual_q)))
                comparison['bones'][name] = dict(component_position_error_cm=float(np.linalg.norm(actual_position-expected_position)),
                                                local_rotation_error_degrees=math.degrees(2*math.acos(min(1., dot))),
                                                expected_component_translation=expected_position.tolist(),
                                                ue_component_translation=actual_position.tolist(),
                                                source_local_scale=src['source_local']['scale'], ue_local_scale=ue['local']['scale'])
            actor = next((a for a in capture.get('actors', []) if a['label'] == 'HCZS_elsa'), None)
            if actor:
                c = actor['component_transform']
                actor_linear = quaternion_matrix(c['rotation']) * np.array(c['scale'])
                observed_points = {name: np.array(observed['bones'][name]['component']['translation']) for name in KEY_BONES}
                component_body = observed_points['bip001 head'] - (observed_points['bip001 l foot']+observed_points['bip001 r foot'])/2
                actual_body = actor_linear @ component_body
                comparison['actual_map_projected_body_degrees'] = float(np.degrees(np.arctan2(right @ actual_body, up @ actual_body)))
                comparison['actor_pitch_yaw_roll'] = actor['actor_rotation']
            result['comparison'].append(comparison)
        result['ue_actors'] = capture.get('actors', [])
        result['rotator_constructor_probe'] = capture.get('rotator_constructor_probe')
        result['validation']['unreal_readback_compared'] = bool(capture.get('passed'))
    result['max_glb_vs_acl_matrix_error'] = max(b['glb_vs_acl_matrix_error'] for s in result['samples'] for b in s['bones'].values())
    write('comparison' + SUFFIX + '.json', result)
    print(json.dumps(dict(source_samples=len(result['samples']), max_glb_vs_acl_matrix_error=result['max_glb_vs_acl_matrix_error'],
                          source_screen_leans=[s['source_lean']['source_projected_body_degrees'] for s in result['samples']],
                          ue_readback_compared=result['validation']['unreal_readback_compared'])))


if __name__ == '__main__':
    if os.environ.get('HCZS_UE_POSE_CAPTURE') == '1':
        capture_unreal()
    else:
        source_audit()
