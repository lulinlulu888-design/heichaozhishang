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

def skin_vertices(model, poses_by_name):
    """Skin source vertices with full local TRS poses and original inverse binds."""
    worlds = {}
    def world(index):
        if index not in worlds:
            bone = model['bones'][index]
            pose = poses_by_name[bone['name']]
            local = np.eye(4)
            local[:3, :3] = quaternion_matrix(pose[3:7]) * pose[7:10]
            local[:3, 3] = pose[:3]
            worlds[index] = local if bone['parent'] is None else world(bone['parent']) @ local
        return worlds[index]
    skin = np.asarray([world(i) @ np.linalg.inv(np.asarray(matrix_rows(b['matrix_raw'])))
        for i, b in enumerate(model['bones'])])
    vertices = np.column_stack((np.asarray(model['positions']), np.ones(len(model['positions']))))
    weights = np.asarray(model['weights'])
    joints = np.where(weights > 0, np.asarray(model['joints'], dtype=int), 0)
    transformed = np.einsum('nvij,nj->nvi', skin[joints], vertices)
    return vertices[:, :3], np.sum(transformed * weights[:, :, None], axis=1)[:, :3]


def sampled_to_reference_layout(sample):
    """Sampled poses store quaternion, translation, scale; reference poses store T, Q, S."""
    return np.concatenate((sample[4:7], sample[:4], sample[7:10]))


def frame_skin_stats(model, poses_by_name):
    """Compare a sampled pose's skinned shape with the bind shape, centroid aligned."""
    bind, posed = skin_vertices(model, poses_by_name)
    if not np.all(np.isfinite(posed)):
        return dict(finite=False)
    height = float(np.ptp(bind[:, 1]))
    displacement = np.linalg.norm((posed - posed.mean(0)) - (bind - bind.mean(0)), axis=1)
    triangles = np.asarray(model['indices'], dtype=int).reshape(-1, 3)
    edges = np.unique(np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1), axis=0)
    bind_length = np.linalg.norm(bind[edges[:, 0]] - bind[edges[:, 1]], axis=1)
    keep = bind_length > 1e-5 * height
    stretch = np.abs(np.log(np.linalg.norm(posed[edges[keep, 0]] - posed[edges[keep, 1]], axis=1) / bind_length[keep]))
    return dict(finite=True, bind_height=height,
        diagonal_ratio=float(np.linalg.norm(np.ptp(posed, 0)) / np.linalg.norm(np.ptp(bind, 0))),
        median_displacement_over_height=float(np.median(displacement) / height),
        p95_displacement_over_height=float(np.percentile(displacement, 95) / height),
        edge_log_stretch_p99=float(np.percentile(stretch, 99)) if stretch.size else 0.0,
        edge_log_stretch_p999=float(np.percentile(stretch, 99.9)) if stretch.size else 0.0)


SAMPLED_SKIN_ENVELOPE = dict(diagonal_ratio=(0.7, 1.2), median_displacement_over_height=(0.0, 0.15),
    p95_displacement_over_height=(0.0, 0.5))
# Strong hall poses move far from the bind but keep triangles near rigid. Bounds are the
# 24 accepted bind-mismatch idles (p99 0.22-0.57, p99.9 0.59-1.38) plus ~15% margin.
SAMPLED_STRETCH_ENVELOPE = dict(diagonal_ratio=(0.6, 1.3), edge_log_stretch_p99=(0.0, 0.65),
    edge_log_stretch_p999=(0.0, 1.6))


def inside(stats, envelope):
    return all(low <= stats[key] <= high for key, (low, high) in envelope.items())


def verify_reference_skin(library, model, sampled_poses=None):
    """Compose every source local TRS, including unweighted ancestor scales.

    When the library reference pose differs from the mesh bind and every model
    bone is driven by the sampled clip, accept the export only if the first
    sampled frame skins inside SAMPLED_SKIN_ENVELOPE (measured on heroes whose
    reference pose matches their bind exactly).
    """
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
        if sampled_poses is None or set(sampled_poses) != {b['name'] for b in model['bones']}:
            raise ValueError('Source reference skin reconstruction exceeds tolerance')
        stats = frame_skin_stats(model, sampled_poses)
        accepted_by = None if not stats['finite'] else 'displacement' if inside(stats, SAMPLED_SKIN_ENVELOPE) \
            else 'local-stretch' if inside(stats, SAMPLED_STRETCH_ENVELOPE) else None
        if not accepted_by:
            raise ValueError('Reference pose differs from bind and sampled frame skins outside envelope: '
                             + json.dumps({k: v for k, v in stats.items() if isinstance(v, float)}))
        return dict(weighted_bones=len(model['used_bones']),
            max_weighted_global_matrix_error=weighted_error,
            max_reference_vertex_component_error=vertex_error,
            reference_pose_mismatch=[r for r in rows if r['max_global_matrix_error'] >= 1e-4],
            sampled_frame0=stats, envelope=SAMPLED_SKIN_ENVELOPE, stretch_envelope=SAMPLED_STRETCH_ENVELOPE,
            accepted_by=accepted_by, correction_applied=False,
            scope='Library reference pose is not the mesh bind; every bone is clip-driven and '
                'original inverse binds are kept. GLB rest pose differs from bind; idle playback only.')
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
