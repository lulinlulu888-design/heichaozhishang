"""Package pinned enemy-991 ACL samples as GLB; no engine or game execution."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np

from export_elsa_model import split_glb, pack_glb
from export_elsa_animation import (sha, read_bounded, save_json, decompose_bind,
    continuous_quaternions, load_clip, validate_roundtrip)
from inspect_neox_animation import parse_library

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'c39eaba279687e3dd1f3c786d627a6738d6aa6138990ffba20bc4990a79095f5'
APK_SHA = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
LIBRARY_SHA = 'cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0'
MODEL_SHA = '21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa'
PINS = {
    'idle': (101, '19eecbdc601b10887652a2b1fa30582e5f71fce270f61d5875cf0ff3facfaf8e',
             'f3701f3ab70cf0998a185463af3d2c8f27f2445d40f18bb2453575c628b90d22'),
    'fire': (36, '5a35d68491d1cf79509f0c966f24d9ec541705e652334f1dbab290f826b8d5a0',
             '4807abe1058d438b2873bb73bd266fe397a142a7063b8e57f6cc6cdca22bdcf6'),
}
LIMITATIONS = [
    'Colour-reference Tex0 only; original purple emission, normal/mix maps and shader are not restored.',
    'Original sample times retained; glTF LINEAR quaternion SLERP differs from ACL normalized LERP between samples.',
    'No animation events, transitions, effects, physics or mapping from fire to a particular battle skill.',
    'CPU validation only; Cocos import, engine playback and visual acceptance remain unverified.',
]


def load_inputs(base_path, recovered):
    base = read_bounded(base_path, 2*1024*1024)
    if sha(base) != BASE_SHA:
        raise ValueError('enemy colour-reference GLB identity mismatch')
    doc, _ = split_glb(base)
    summary_raw = read_bounded(recovered/'summary.json', 1024*1024)
    summary = json.loads(summary_raw)
    library = parse_library(read_bounded(recovered/'library.gisacl', 1024*1024))
    if (library['sha256'] != LIBRARY_SHA or summary['library_sha256'] != LIBRARY_SHA or
            summary['apk_sha256'] != APK_SHA or summary['model_sha256'] != MODEL_SHA):
        raise ValueError('enemy source provenance mismatch')
    joints = doc['skins'][0]['joints']
    names = [doc['nodes'][node]['name'] for node in joints]
    if len(names) != 61 or names != summary['model_names']:
        raise ValueError('enemy bone identity mismatch')
    clips = []
    for name, (frames, wrapper_sha, pose_sha) in PINS.items():
        clip = load_clip(recovered, name, library, names)
        if (clip['metadata']['sha256'] != wrapper_sha or clip['pose_sha256'] != pose_sha or
                clip['metadata']['source']['apk_sha256'] != APK_SHA or
                clip['frames'] != frames or clip['rate'] != 30.0 or clip['values'].shape != (frames, 61, 10)):
            raise ValueError(f'{name}: pinned clip identity mismatch')
        mapping = clip['mapping']
        if ({r['clip_index'] for r in mapping} != set(range(61)) or
                {r['mesh_joint'] for r in mapping} != set(range(61)) or len(mapping) != 61):
            raise ValueError('incomplete or duplicate bone mapping')
        clips.append(clip)
    return base, clips, sha(summary_raw)


def encode(base, clips, expected_names=None):
    doc, binary = split_glb(base)
    if doc.get('animations') or len(doc.get('skins', [])) != 1:
        raise ValueError('expected static single-skin source')
    joints = doc['skins'][0]['joints']
    if len(joints) != 61 or [c['name'] for c in clips] != (list(PINS) if expected_names is None else list(expected_names)):
        raise ValueError('unexpected enemy skeleton or clip list')
    errors = []
    for index in joints:
        node = doc['nodes'][index]
        trs, error = decompose_bind(node.pop('matrix'))
        node.update(trs)
        errors.append(error)

    def append(values, kind, bounds=False):
        data = np.asarray(values, dtype='<f4')
        if not np.all(np.isfinite(data)):
            raise ValueError('nonfinite animation data')
        while len(binary) % 4:
            binary.append(0)
        blob = data.tobytes(order='C')
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(blob)})
        binary.extend(blob)
        accessor = {'bufferView': len(doc['bufferViews'])-1, 'componentType': 5126,
                    'count': len(data), 'type': kind}
        if bounds:
            accessor.update(min=[float(data.min())], max=[float(data.max())])
        doc['accessors'].append(accessor)
        return len(doc['accessors'])-1

    doc['animations'] = []
    reports = []
    for clip in clips:
        values = clip['values']
        quaternions, sign_changes = continuous_quaternions(values[:, :, :4])
        times = (np.arange(clip['frames'], dtype=np.float64)/clip['rate']).astype('<f4')
        if not np.all(np.diff(times) > 0):
            raise ValueError('sample times lost order')
        input_index = append(times, 'SCALAR', True)
        anim = {'name': clip['name'], 'channels': [], 'samplers': [], 'extras': {
            'sourcePoseSha256': clip['pose_sha256'], 'sourceMetadataSha256': clip['metadata_sha256'],
            'sourceFrames': clip['frames'], 'sourceSampleRate': clip['rate'],
            'quaternionSignChanges': sign_changes, 'bindCorrectionApplied': False,
            'interpolationScope': LIMITATIONS[1]}}
        for mapping in clip['mapping']:
            track, node = mapping['clip_index'], joints[mapping['mesh_joint']]
            for path, data, kind in (
                ('translation', values[:, track, 4:7], 'VEC3'),
                ('rotation', quaternions[:, track], 'VEC4'),
                ('scale', values[:, track, 7:10], 'VEC3')):
                output_index = append(data, kind)
                anim['channels'].append({'sampler': len(anim['samplers']), 'target': {'node': node, 'path': path}})
                anim['samplers'].append({'input': input_index, 'output': output_index, 'interpolation': 'LINEAR'})
        doc['animations'].append(anim)
        reports.append({'name': clip['name'], 'frames': clip['frames'], 'sample_rate': clip['rate'],
            'duration_source_seconds': (clip['frames']-1)/clip['rate'],
            'duration_gltf_seconds': float(times[-1]), 'channels': len(anim['channels']),
            'pose_sha256': clip['pose_sha256'], 'metadata_sha256': clip['metadata_sha256'],
            'source': clip['metadata']['source'], 'bone_mapping': clip['mapping'],
            'sampler_executable_sha256': clip['metadata']['sampler_executable_sha256'],
            'quaternion_sign_changes': sign_changes})
    doc['asset']['generator'] += ' / enemy-991 original ACL sampled animation exporter'
    doc['extras']['missing'] = [
        'Animation events, transitions, particles, triggers, music and physics are not included in this GLB.'
        if item == 'Animation clips, particles, triggers, music and physics are not included in this GLB.' else item
        for item in doc['extras']['missing']]
    doc.setdefault('extras', {})['animationRecovery'] = {
        'baseGlbSha256': sha(base), 'sourceApkSha256': APK_SHA, 'librarySha256': LIBRARY_SHA,
        'bindCorrectionApplied': False, 'enginePlaybackVerified': False, 'limitations': LIMITATIONS}
    return pack_glb(doc, binary), reports, max(errors)


def run(base_path, recovered, out):
    base, clips, summary_sha = load_inputs(base_path, recovered)
    glb, reports, error = encode(base, clips)
    verification = validate_roundtrip(base, glb, clips)
    if sum(row['sample_count_verified'] for row in verification) != 8357:
        raise ValueError('incomplete animation sample verification')
    for row in verification:
        if row['moving_tracks'] < 1 or row['max_vertex_displacement_from_first_frame'] < .001:
            raise ValueError('expected original enemy motion is absent')
    out.mkdir(parents=True, exist_ok=True)
    target = out/'tutorial-enemy-991.animated.glb'
    temporary = target.with_suffix('.glb.pending')
    temporary.write_bytes(glb)
    temporary.replace(target)
    doc, _ = split_glb(glb)
    report = {'base_glb': str(base_path.resolve()), 'base_glb_sha256': sha(base),
        'source_apk_sha256': APK_SHA, 'library_sha256': LIBRARY_SHA,
        'recovered_summary_sha256': summary_sha, 'glb_sha256': sha(glb), 'glb_bytes': len(glb),
        'output': str(target.resolve()), 'bone_count': 61, 'max_bind_matrix_to_trs_error': error,
        'inverse_bind_matrices': 'Original bytes, accessor and joint ordering preserved.',
        'clips': reports, 'verification': verification, 'limitations': LIMITATIONS,
        'engine_playback_verified': False, 'game_code_executed': False}
    save_json(out/'export-report.json', report)
    save_json(out/'gltf.json', doc)
    save_json(out/'manifest.json', {'schemaVersion': 1, 'file': target.name, 'bytes': len(glb),
        'glbSha': sha(glb), 'baseGlbSha': sha(base), 'clipNames': list(PINS), 'report': 'export-report.json',
        'scope': 'Original enemy idle/fire samples and colour-reference material; CPU verified only.'})
    return {key: report[key] for key in ('output', 'glb_bytes', 'glb_sha256', 'max_bind_matrix_to_trs_error', 'verification')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=ROOT/'analysis/tutorial-enemy/tutorial-enemy-991.colour-reference.glb')
    parser.add_argument('--recovered', type=Path, default=ROOT/'analysis/tutorial-enemy-animation')
    parser.add_argument('--out', type=Path, default=ROOT/'analysis/tutorial-enemy-animated')
    args = parser.parse_args()
    print(json.dumps(run(args.base, args.recovered, args.out), indent=2))
