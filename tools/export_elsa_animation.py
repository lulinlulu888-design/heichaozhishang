"""Attach two source-verified ACL-sampled clips to Elsa's colour-reference GLB.

Does not load game code or an engine. Original inverse bind matrices and mesh
bytes remain unchanged. Animation q/t/s samples are preserved (only equivalent
quaternion signs may change); no bind-pose correction is applied.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from export_elsa_model import split_glb, pack_glb
from inspect_neox_animation import parse_library, parse_clip, map_bones, summarize_poses

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '84956d9eeec1285c4de49faa6f0def6453663f288fb40352cf23deec6479a35f'
CLIP_NAMES = ('stand_idle', 'skin')
MAX_BYTES = 80_000_020


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, maximum=MAX_BYTES):
    with path.open('rb') as f:
        data = f.read(maximum+1)
    if len(data) > maximum:
        raise ValueError(f'{path.name}: file exceeds budget')
    return data


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def quaternion_matrix(q):
    """Unit quaternion orientation, accepting floating-point roundoff only."""
    q = np.asarray(q, dtype=np.float64)
    norm = np.linalg.norm(q, axis=-1, keepdims=True)
    if not np.all(np.isfinite(q)) or np.any(np.abs(norm-1) > .001):
        raise ValueError('invalid quaternion')
    x, y, z, w = np.moveaxis(q/norm, -1, 0)
    return np.stack((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w),
                     2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w),
                     2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)), axis=-1).reshape(q.shape[:-1]+(3, 3))


def rotation_quaternion(r):
    # Convert a verified orthogonal matrix to xyzw. The largest-component
    # branch avoids precision loss around rotations of 180 degrees.
    candidates = np.array([1+r[0, 0]-r[1, 1]-r[2, 2],
                           1-r[0, 0]+r[1, 1]-r[2, 2],
                           1-r[0, 0]-r[1, 1]+r[2, 2], 1+np.trace(r)])
    i = int(np.argmax(candidates))
    q = np.zeros(4)
    q[i] = math.sqrt(max(0, candidates[i]))*.5
    den = 4*q[i]
    if i == 3:
        q[:3] = [(r[2, 1]-r[1, 2])/den, (r[0, 2]-r[2, 0])/den, (r[1, 0]-r[0, 1])/den]
    else:
        j, k = (i+1) % 3, (i+2) % 3
        q[j] = (r[j, i]+r[i, j])/den
        q[k] = (r[k, i]+r[i, k])/den
        q[3] = (r[k, j]-r[j, k])/den
    q /= np.linalg.norm(q)
    if q[3] < 0:
        q = -q
    return q


def decompose_bind(column_major):
    m = np.asarray(column_major, dtype=np.float64).reshape(4, 4).T
    if not np.all(np.isfinite(m)) or np.max(np.abs(m[3]-[0, 0, 0, 1])) > 1e-8:
        raise ValueError('non-affine bind matrix')
    scale = np.linalg.norm(m[:3, :3], axis=0)
    if np.any(scale < 1e-8) or np.linalg.det(m[:3, :3]) <= 0:
        raise ValueError('unsupported singular/reflected bind matrix')
    rotation = m[:3, :3]/scale
    if np.max(np.abs(rotation.T@rotation-np.eye(3))) > 1e-5:
        raise ValueError('bind matrix has unsupported shear')
    u, _, vh = np.linalg.svd(rotation)
    q = rotation_quaternion(u@vh)
    reconstructed = np.eye(4)
    reconstructed[:3, :3] = quaternion_matrix(q)*scale
    reconstructed[:3, 3] = m[:3, 3]
    error = float(np.max(np.abs(reconstructed-m)))
    if error > 2e-6:
        raise ValueError('TRS cannot preserve bind matrix within tolerance')
    return {'translation': m[:3, 3].tolist(), 'rotation': q.tolist(), 'scale': scale.tolist()}, error


def continuous_quaternions(values):
    result = np.array(values, dtype='<f4', copy=True)
    if result.ndim != 3 or result.shape[2] != 4 or not np.all(np.isfinite(result)):
        raise ValueError('expected finite frame/bone/xyzw quaternions')
    errors = np.abs(np.sum(result.astype(np.float64)**2, axis=-1)-1)
    if np.any(errors >= .001):
        raise ValueError('nonunit animation quaternion')
    changed = 0
    for frame in range(1, len(result)):
        flip = np.sum(result[frame-1].astype(np.float64)*result[frame], axis=1) < 0
        result[frame, flip] *= -1
        changed += int(np.sum(flip))
    return result, changed


def load_clip(directory, name, library, model_names):
    metadata_raw = read_bounded(directory/(name+'.json'), 2*1024*1024)
    metadata = json.loads(metadata_raw)
    source = read_bounded(directory/(name+'.gisacl'), 32*1024*1024)
    parsed = parse_clip(source)
    if metadata['sha256'] != sha(source) or metadata['source']['sha256'] != sha(source):
        raise ValueError('clip wrapper source hash mismatch')
    acl = source[parsed['acl_offset']:]
    fnv = 2166136261
    for byte in acl[8:]:
        fnv = ((fnv ^ byte)*16777619) & 0xffffffff
    if f'{fnv:08x}' != parsed['acl_fnv32']:
        raise ValueError('ACL embedded hash mismatch')
    sampler = metadata.get('sampler', {})
    if (metadata.get('acl_hash_verified') is not True or sampler.get('hashVerified') is not True
            or sampler.get('inputSha256') != parsed['acl_sha256']
            or metadata['acl_sha256'] != parsed['acl_sha256']
            or sampler.get('aclVersion') != '1.2.0' or sampler.get('binaryVersion') != 4):
        raise ValueError('clip lacks verified ACL sampler provenance')
    mapping = map_bones(library, parsed, model_names)
    if mapping != metadata['bone_mapping']:
        raise ValueError('recorded mapping differs from bone identity mapping')
    raw = read_bounded(directory/(name+'.poses'))
    pose = summarize_poses(raw)
    if sha(raw) != metadata['poses']['sha256']:
        raise ValueError('pose source hash mismatch')
    if (pose['bone_count'], pose['frames'], pose['sample_rate']) != (
            parsed['bone_count'], parsed['samples'], parsed['sample_rate']):
        raise ValueError('pose counts/rate differ from ACL')
    values = np.frombuffer(raw, dtype='<f4', offset=20).reshape(pose['frames'], pose['bone_count'], 10).copy()
    return {'name': name, 'metadata': metadata, 'metadata_sha256': sha(metadata_raw),
            'pose_sha256': sha(raw), 'values': values, 'mapping': mapping,
            'frames': pose['frames'], 'rate': pose['sample_rate'], 'raw_bytes': len(raw)}


def accessor_array(doc, binary, index):
    a = doc['accessors'][index]
    view = doc['bufferViews'][a['bufferView']]
    dtype = {5121: 'u1', 5123: '<u2', 5126: '<f4'}[a['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    start = view.get('byteOffset', 0)+a.get('byteOffset', 0)
    length = np.dtype(dtype).itemsize*a['count']*width
    if 'byteStride' in view or start % 4 or start+length > view.get('byteOffset', 0)+view['byteLength'] or start+length > len(binary):
        raise ValueError('unsupported or out-of-bounds accessor')
    return np.frombuffer(binary, dtype=dtype, offset=start, count=a['count']*width).reshape(a['count'], width)


def encode(base, clips):
    doc, binary = split_glb(base)
    if doc.get('animations') or len(doc.get('skins', [])) != 1:
        raise ValueError('expected static single-skin source')
    joints = doc['skins'][0]['joints']
    node_name_changes = []
    for index, node in enumerate(doc['nodes']):
        source_name = node.get('name', '')
        if '/' not in source_name and '\\' not in source_name:
            continue
        if index in joints:
            raise ValueError('bone name contains an unsupported hierarchy separator')
        new_name = 'ElsaMesh' if 'mesh' in node else f'ElsaNode{index}'
        if any(other.get('name') == new_name for other in doc['nodes']):
            raise ValueError('portable node name would collide')
        node['name'] = new_name
        node.setdefault('extras', {})['sourceNodeName'] = source_name
        node_name_changes.append({'node': index, 'source_name': source_name, 'name': new_name})
    doc['extras']['nodeNameChanges'] = node_name_changes
    bind_errors = []
    for node_index in joints:
        node = doc['nodes'][node_index]
        trs, error = decompose_bind(node['matrix'])
        del node['matrix']
        node.update(trs)
        bind_errors.append(error)

    def append(rows, typ, bounds=False):
        rows = np.asarray(rows, dtype='<f4')
        if not np.all(np.isfinite(rows)):
            raise ValueError('nonfinite animation data')
        while len(binary) % 4:
            binary.append(0)
        blob = rows.tobytes(order='C')
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(blob)})
        binary.extend(blob)
        result = {'bufferView': len(doc['bufferViews'])-1, 'componentType': 5126,
                  'count': len(rows), 'type': typ}
        if bounds:
            result.update(min=[float(np.min(rows))], max=[float(np.max(rows))])
        doc['accessors'].append(result)
        return len(doc['accessors'])-1

    doc['animations'] = []
    reports = []
    for clip in clips:
        data = clip['values']
        quaternions, sign_changes = continuous_quaternions(data[:, :, :4])
        times = (np.arange(clip['frames'], dtype=np.float64)/clip['rate']).astype('<f4')
        if not np.all(np.diff(times) > 0):
            raise ValueError('float32 time quantization loses frame order')
        input_index = append(times, 'SCALAR', True)
        anim = {'name': clip['name'], 'channels': [], 'samplers': [],
                'extras': {'sourcePoseSha256': clip['pose_sha256'], 'sourceMetadataSha256': clip['metadata_sha256'],
                           'sourceSampleRate': clip['rate'], 'sourceFrames': clip['frames'],
                           'quaternionSignChanges': sign_changes,
                           'interpolationScope': 'Original sample times; glTF LINEAR rotation uses SLERP, while ACL 1.2.0 uses normalized LERP between samples.',
                           'bindCorrection': 'None. Original mesh inverse bind matrices and source local poses preserved.'}}
        for row in clip['mapping']:
            track, node = row['clip_index'], joints[row['mesh_joint']]
            for path, values, typ in [('translation', data[:, track, 4:7], 'VEC3'),
                                       ('rotation', quaternions[:, track, :], 'VEC4'),
                                       ('scale', data[:, track, 7:10], 'VEC3')]:
                output_index = append(values, typ)
                anim['channels'].append({'sampler': len(anim['samplers']), 'target': {'node': node, 'path': path}})
                anim['samplers'].append({'input': input_index, 'output': output_index, 'interpolation': 'LINEAR'})
        doc['animations'].append(anim)
        reports.append({'name': clip['name'], 'frames': clip['frames'], 'sample_rate': clip['rate'],
                        'duration_source_seconds': (clip['frames']-1)/clip['rate'],
                        'duration_gltf_seconds': float(times[-1]), 'channels': len(anim['channels']),
                        'quaternion_sign_changes': sign_changes, 'pose_sha256': clip['pose_sha256'],
                        'metadata_sha256': clip['metadata_sha256'], 'source': clip['metadata']['source'],
                        'sampler_executable_sha256': clip['metadata']['sampler_executable_sha256'],
                        'bone_mapping': clip['mapping']})
    doc['asset']['generator'] += ' / source ACL sampled animation exporter'
    doc['extras']['missing'] = [x for x in doc['extras'].get('missing', []) if x != 'animation clips and physics']
    doc['extras']['missing'].extend(['animation events, transitions, physics and original game logic',
                                    'exact between-sample ACL quaternion interpolation'])
    doc['extras']['animationSourceBaseGlbSha256'] = sha(base)
    doc['extras']['knownBindDifference'] = {'meshJoint': 50, 'name': 'bip001 r toe0',
                                           'referenceToMeshDegrees': 3.811740265875115,
                                           'affectedVertices': 39, 'correctionApplied': False}
    return pack_glb(doc, binary), reports, max(bind_errors)


def validate_roundtrip(base, glb, clips):
    """Re-read every output sample and bound skinned positions across all frames."""
    original, original_binary = split_glb(base)
    doc, binary = split_glb(glb)
    original_length = original['buffers'][0]['byteLength']
    if binary[:original_length] != original_binary[:original_length]:
        raise ValueError('original mesh/IBM/texture bytes were changed')
    for key in ('skins', 'meshes', 'materials', 'textures', 'images', 'samplers'):
        if doc[key] != original[key]:
            raise ValueError(f'original {key} changed')
    joints = doc['skins'][0]['joints']
    parents = {child: i for i, n in enumerate(doc['nodes']) for child in n.get('children', [])}
    model_arrays = {key: np.concatenate([accessor_array(doc, binary, p['attributes'][key])
                                        for p in doc['meshes'][0]['primitives']])
                    for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}
    vertices = np.column_stack((model_arrays['POSITION'], np.ones(len(model_arrays['POSITION']))))
    js, ws = model_arrays['JOINTS_0'], model_arrays['WEIGHTS_0'].astype(np.float64)
    ibms = accessor_array(doc, binary, doc['skins'][0]['inverseBindMatrices']).astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1)
    if np.any(js >= len(joints)):
        raise ValueError('skin influence outside joint array')
    result = []
    for anim, clip in zip(doc['animations'], clips):
        raw = clip['values']
        recovered = np.empty_like(raw)
        by_node = {joints[row['mesh_joint']]: row['clip_index'] for row in clip['mapping']}
        targets = set()
        max_time_error = 0.0
        for channel in anim['channels']:
            node, path = channel['target']['node'], channel['target']['path']
            if (node, path) in targets or 'matrix' in doc['nodes'][node]:
                raise ValueError('duplicate channel or matrix on animated node')
            targets.add((node, path))
            s = anim['samplers'][channel['sampler']]
            if s['interpolation'] != 'LINEAR':
                raise ValueError('unexpected interpolation')
            times = accessor_array(doc, binary, s['input'])[:, 0]
            expected_times = (np.arange(clip['frames'], dtype=np.float64)/clip['rate']).astype('<f4')
            if not np.array_equal(times, expected_times):
                raise ValueError('times differ from original sample rate')
            max_time_error = max(max_time_error, float(np.max(np.abs(times-np.arange(clip['frames'])/clip['rate']))))
            values = accessor_array(doc, binary, s['output'])
            sl = {'rotation': slice(0, 4), 'translation': slice(4, 7), 'scale': slice(7, 10)}[path]
            expected = raw[:, by_node[node], sl]
            if path == 'rotation':
                same = np.all(values == expected, axis=1) | np.all(values == -expected, axis=1)
                if not np.all(same) or np.any(np.sum(values[:-1].astype(np.float64)*values[1:], axis=1) < 0):
                    raise ValueError('rotations differ from source or have discontinuous signs')
            elif not np.array_equal(values, expected):
                raise ValueError('translation/scale differs from source')
            recovered[:, by_node[node], sl] = values
        if len(targets) != len(joints)*3:
            raise ValueError('incomplete skeleton animation')

        local_by_node = {}
        for node, track in by_node.items():
            p = recovered[:, track]
            local = np.tile(np.eye(4), (clip['frames'], 1, 1))
            local[:, :3, :3] = quaternion_matrix(p[:, :4])*p[:, None, 7:10]
            local[:, :3, 3] = p[:, 4:7]
            local_by_node[node] = local
        worlds = {}
        visiting = set()
        def world(node):
            if node in worlds:
                return worlds[node]
            if node in visiting:
                raise ValueError('node parent cycle')
            visiting.add(node)
            local = local_by_node.get(node)
            if local is None:
                n = doc['nodes'][node]
                if 'matrix' in n:
                    local = np.array(n['matrix']).reshape(4, 4).T
                elif any(k in n for k in ('rotation', 'translation', 'scale')):
                    raise ValueError('unexpected unanimated transformed ancestor')
                else:
                    local = np.eye(4)
            worlds[node] = world(parents[node])@local if node in parents else local
            visiting.remove(node)
            return worlds[node]
        joint_world = np.stack([world(node) for node in joints], axis=1)
        skin = joint_world@ibms
        first = None
        moved = np.zeros(len(vertices), dtype=bool)
        min_bound, max_bound = np.full(3, np.inf), np.full(3, -np.inf)
        max_displacement = 0.0
        sampled_frame_bounds = []
        selected_frames = {0, (clip['frames']-1)//2, clip['frames']-1}
        for frame in range(clip['frames']):
            posed = np.einsum('vjik,vk->vji', skin[frame, js], vertices)
            positions = np.sum(posed*ws[:, :, None], axis=1)[:, :3]
            if not np.all(np.isfinite(positions)) or np.max(np.abs(positions)) > 1e4:
                raise ValueError('nonfinite or unbounded skinned positions')
            if first is None:
                first = positions.copy()
            displacement = np.linalg.norm(positions-first, axis=1)
            moved |= displacement > 1e-4
            max_displacement = max(max_displacement, float(displacement.max()))
            min_bound = np.minimum(min_bound, positions.min(axis=0))
            max_bound = np.maximum(max_bound, positions.max(axis=0))
            if frame in selected_frames:
                sampled_frame_bounds.append({'frame': frame, 'seconds': frame/clip['rate'],
                    'min': positions.min(axis=0).tolist(), 'max': positions.max(axis=0).tolist(),
                    'max_displacement_from_first_frame': float(displacement.max()),
                    'vertices_moving_over_1e_4': int(np.sum(displacement > 1e-4))})
        moving_tracks = int(np.sum(np.any(np.ptp(recovered, axis=0) > 1e-6, axis=1)))
        if clip['name'] == 'stand_idle' and (max_displacement < 1e-3 or not moving_tracks):
            raise ValueError('expected visible idle motion is absent')
        if clip['name'] == 'skin' and (moving_tracks or max_displacement > 1e-10):
            raise ValueError('source constant skin clip was changed')
        result.append({'name': clip['name'], 'sample_count_verified': clip['frames']*len(joints),
                       'channel_count_verified': len(targets), 'pose_values': 'exact float32 except equivalent quaternion sign',
                       'max_timestamp_rounding_seconds': max_time_error, 'moving_tracks': moving_tracks,
                       'max_vertex_displacement_from_first_frame': max_displacement,
                       'vertices_moving_over_1e_4': int(np.sum(moved)),
                       'all_frame_skinned_bounds': {'min': min_bound.tolist(), 'max': max_bound.tolist()},
                       'selected_frame_bounds': sampled_frame_bounds,
                       'motion_scope': 'CPU reconstruction at every original frame; not evidence of engine playback.'})
    return result


def run(base_path, recovered_dir, out):
    base = read_bounded(base_path, 16*1024*1024)
    if sha(base) != BASE_SHA:
        raise ValueError('colour-reference GLB identity changed')
    doc, _ = split_glb(base)
    summary_raw = read_bounded(recovered_dir/'summary.json', 1024*1024)
    summary = json.loads(summary_raw)
    library_raw = read_bounded(recovered_dir/'ailisha.gisacl', 32*1024*1024)
    library = parse_library(library_raw)
    if library['sha256'] != summary['library_sha256'] or summary['model_sha256'] != doc['extras']['sourceSha256']:
        raise ValueError('animation library/model identity mismatch')
    names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
    clips = [load_clip(recovered_dir, name, library, names) for name in CLIP_NAMES]
    for clip in clips:
        if clip['metadata']['source']['apk_sha256'] != summary['apk_sha256']:
            raise ValueError('animation APK provenance mismatch')
    glb, reports, bind_error = encode(base, clips)
    verification = validate_roundtrip(base, glb, clips)
    exported_doc, _ = split_glb(glb)
    report = {'base_glb': str(base_path.resolve()), 'base_glb_sha256': sha(base),
              'source_apk_sha256': summary['apk_sha256'], 'library_sha256': library['sha256'],
              'recovered_summary_sha256': sha(summary_raw), 'glb_sha256': sha(glb), 'glb_bytes': len(glb),
              'bone_count': len(names), 'max_bind_matrix_to_trs_error': bind_error,
              'inverse_bind_matrices': 'Original bytes/accessor/skin joint ordering unchanged',
              'node_name_changes': exported_doc['extras']['nodeNameChanges'],
              'clips': reports, 'verification': verification,
              'known_bind_difference': doc['extras'].get('knownBindDifference', {
                  'mesh_joint': 50, 'name': 'bip001 r toe0', 'degrees': 3.811740265875115,
                  'affected_vertices': 39, 'correction_applied': False}),
              'limitations': ['glTF LINEAR uses quaternion SLERP; ACL v1.2 uses normalized LERP between frames.',
                              'No animation events/transitions/physics or original toon shader restoration.',
                              'Numerical validation is not actual Cocos playback verification.']}
    out.mkdir(parents=True, exist_ok=True)
    target = out/'elsa-yangcheng.animated.glb'
    pending = out/'elsa-yangcheng.animated.glb.pending'
    pending.write_bytes(glb)
    pending.replace(target)
    report['output'] = str(target.resolve())
    save_json(out/'export-report.json', report)
    save_json(out/'manifest.json', {'schemaVersion': 1, 'file': target.name,
        'glbSha': sha(glb), 'bytes': len(glb), 'clipNames': list(CLIP_NAMES),
        'baseGlbSha': sha(base), 'report': 'export-report.json',
        'scope': 'Real source animation samples with colour-reference materials; CPU verified, engine playback not verified.'})
    save_json(out/'gltf.json', exported_doc)
    return {k: report[k] for k in ('output', 'glb_bytes', 'glb_sha256', 'max_bind_matrix_to_trs_error', 'verification')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=ROOT/'analysis/elsa-model/elsa-yangcheng.colour-reference.glb')
    p.add_argument('--recovered', type=Path, default=ROOT/'analysis/animation/recovered')
    p.add_argument('--out', type=Path, default=ROOT/'analysis/elsa-animation')
    args = p.parse_args()
    print(json.dumps(run(args.base, args.recovered, args.out), indent=2))
