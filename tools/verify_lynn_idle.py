"""Check sampled Lynn motion and source bind conventions without rendering."""
import json
from pathlib import Path
from inspect_neox_animation import file_sha256, parse_library, save_json
from inspect_neox_model import parse_model
from sample_tutorial_enemy_animation import reference_bind_comparison, motion_summary
import numpy as np
from inspect_neox_model import matrix_rows
from export_elsa_animation import quaternion_matrix

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/characters/lynn/idle'

def verify_reference_skin(library, model):
    """Compose every source local TRS, including unweighted ancestor scales."""
    reference = dict(zip(library['bone_names'], library['reference_pose']))
    worlds = {}
    def world(index):
        if index in worlds:
            return worlds[index]
        bone = model['bones'][index]
        pose = reference[bone['name']]
        local = np.eye(4)
        local[:3, :3] = quaternion_matrix(pose[3:7]) * pose[7:10]
        local[:3, 3] = pose[:3]
        worlds[index] = local if bone['parent'] is None else world(bone['parent']) @ local
        return worlds[index]
    rows, skin = [], []
    for index, bone in enumerate(model['bones']):
        mesh = np.asarray(matrix_rows(bone['matrix_raw']))
        composed = world(index)
        error = float(np.max(np.abs(composed-mesh)))
        rows.append(dict(index=index, name=bone['name'], weighted=index in model['used_bones'],
            max_global_matrix_error=error))
        skin.append(composed @ np.linalg.inv(mesh))
    skin = np.asarray(skin)
    vertices = np.column_stack((np.asarray(model['positions']), np.ones(len(model['positions']))))
    joints = np.asarray(model['joints'], dtype=int)
    weights = np.asarray(model['weights'])
    if np.any((joints >= len(skin)) & (weights > 0)):
        raise ValueError('Weighted joint outside skeleton')
    joints = np.where(weights > 0, joints, 0)  # Source unused slots use sentinel 255.
    transformed = np.einsum('nvij,nj->nvi', skin[joints], vertices)
    reconstructed = np.sum(transformed * weights[:,:,None], axis=1)
    vertex_error = float(np.max(np.abs(reconstructed[:,:3]-vertices[:,:3])))
    weighted_error = max(r['max_global_matrix_error'] for r in rows if r['weighted'])
    if weighted_error >= 1e-4 or vertex_error >= 1e-4:
        raise ValueError('Source reference skin reconstruction exceeds tolerance')
    return dict(weighted_bones=len(model['used_bones']),
        max_weighted_global_matrix_error=weighted_error,
        max_reference_vertex_component_error=vertex_error,
        unweighted_mismatches=[r for r in rows if not r['weighted'] and r['max_global_matrix_error']>=1e-4],
        all_parent_transforms_preserved=True, correction_applied=False,
        scope='CPU reference pose only; sampled animation rendering remains unverified')

def main():
    audit = json.loads((OUT.parent/'asset-audit.json').read_text('utf8'))
    clip = json.loads((OUT/'idle_1.json').read_text('utf8'))
    def read(logical):
        record = audit['sources'][logical]
        path = Path(record['sample_path'])
        if file_sha256(path) != record['sha256']:
            raise ValueError('Source changed')
        return path.read_bytes()
    library = parse_library(read('character\\player\\lin\\lin.gisacl'), allow_empty_roots=True)
    if library['sha256'] != clip['library_sha256']:
        raise ValueError('Library identity changed')
    pose_path = OUT/'idle_1.poses'
    if file_sha256(pose_path) != clip['poses']['sha256'] or not clip['acl_hash_verified']:
        raise ValueError('Pose provenance mismatch')
    comparisons = {logical: reference_bind_comparison(library, parse_model(read(logical)))
        for logical in clip['bone_mappings']}
    reference_skin = {logical: verify_reference_skin(library, parse_model(read(logical)))
        for logical in clip['bone_mappings']}
    motion = motion_summary(pose_path.read_bytes(), next(iter(clip['bone_mappings'].values())))
    save_json(OUT/'bind-comparison.json', comparisons)
    save_json(OUT/'motion.json', motion)
    save_json(OUT/'reference-skin.json', reference_skin)
    report = dict(moving_bones=motion['moving_bones'],
        max_bind_errors={k:v['max_local_matrix_component_error'] for k,v in comparisons.items()},
        source_library_duration_ms=clip['library_record']['duration_ms'],
        sampled_duration_seconds=clip['duration_seconds'],
        scale_range=clip['poses']['scale_range'],
        reference_skin={k:{field:v[field] for field in ('weighted_bones',
            'max_weighted_global_matrix_error','max_reference_vertex_component_error')} for k,v in reference_skin.items()},
        limits=['Source duration and sampled duration differ; no timing correction applied.',
            'Nonunit scale is preserved; no unit-scale replacement or retargeting.',
            'No GLB export, engine skinning or visual playback verified.'])
    save_json(OUT/'verification.json', report)
    print(json.dumps(report))

if __name__ == '__main__':
    main()
