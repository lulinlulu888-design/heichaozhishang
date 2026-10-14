"""Recover exactly the pinned tutorial enemy idle/fire ACL data samples.

Never executes APK code. Uses the existing official ACL 1.2.0 data decoder,
whose C++ SHA allowlist is the boundary before its incomplete layout validator.
No arbitrary ACL input, skeleton, retargeting, or animation correction is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from inspect_neox_animation import (parse_library, parse_clip, map_bones, clip_path,
    file_sha256, sample_clip, summarize_poses, extract_with_provenance, save_json)
from inspect_neox_model import parse_model, matrix_rows
from neox_resource_paths import read_catalogue
from export_elsa_animation import quaternion_matrix

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/tutorial-enemy-animation'
SOURCE = ROOT/'analysis/first-encounter'
APK_SHA = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
RESOURCE_SHA = 'eec6d24ba0c3d71f82c43cd1e44d3a0d640ee40dc9fe88bc7a5e9d98d82630a1'
LIBRARY_SHA = 'cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0'
MODEL_SHA = '21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa'
LIBRARY_PATH = 'character/monster/yuanjieguai_yijiemofang/yuanjieguai_yijiemofang.gisacl'
SAMPLER_ROOT = ROOT/'tools/runtime/acl-1.2.0'
SAMPLER = SAMPLER_ROOT/'build/Release/acl-sample.exe'
ACL_SOURCE_SHA = '167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8'
WRAPPER_SHA = 'c2f3e96fc84a7413fd1b060cbea77b48b3cf3818c8b4fc0a754d9802d2b1fdd8'
CLIPS = {
    'idle': {'library_index': 3, 'npk_index': 3383, 'offset': 19735572,
        'wrapper_sha256': '19eecbdc601b10887652a2b1fa30582e5f71fce270f61d5875cf0ff3facfaf8e',
        'acl_sha256': '26de4e5657227f27f19f64dc2c91aefe1dc5c23face79af10cb8811d5bc88a3f',
        'samples': 101, 'sample_rate': 30.0, 'segments': 6},
    'fire': {'library_index': 0, 'npk_index': 7051, 'offset': 19568148,
        'wrapper_sha256': '5a35d68491d1cf79509f0c966f24d9ec541705e652334f1dbab290f826b8d5a0',
        'acl_sha256': '7615d852c5356a2dd11f2c2e7fc04953e21a71bb5364e245fafaa8de4decbfbc',
        'samples': 36, 'sample_rate': 30.0, 'segments': 2},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(path, maximum=32*1024*1024):
    with path.open('rb') as stream:
        data = stream.read(maximum+1)
    if len(data) > maximum:
        raise ValueError(f'{path.name}: byte budget exceeded')
    return data


def pinned(path, expected):
    data = bounded(path)
    if sha(data) != expected:
        raise ValueError(f'{path.name}: pinned SHA-256 mismatch')
    return data


def fnv32(data):
    result = 2166136261
    for value in data:
        result = ((result ^ value)*16777619) & 0xffffffff
    return result


def inputs():
    resources = json.loads(pinned(SOURCE/'resources.json', RESOURCE_SHA))
    if resources['apk_sha256'] != APK_SHA:
        raise ValueError('resource catalogue APK identity changed')
    library_raw = pinned(SOURCE/'enemy-model.gisacl', LIBRARY_SHA)
    model_raw = pinned(SOURCE/'enemy-model.mesh', MODEL_SHA)
    library, model = parse_library(library_raw), parse_model(model_raw)
    if library['bone_count'] != 61 or len(model['bones']) != 61 or library['clip_count'] != 8:
        raise ValueError('unexpected tutorial skeleton/library count')
    entries = {entry['output']: entry for entry in resources['entries']}
    for name, index, expected in [('enemy-model.gisacl', 6081, LIBRARY_SHA), ('enemy-model.mesh', 1902, MODEL_SHA)]:
        source = entries[name]
        if (source['index'], source['sha256'], source['member'], source['apk_sha256']) != (index, expected, 'assets/res/character.npk', APK_SHA):
            raise ValueError('source chain identity mismatch')
    library['source'] = entries['enemy-model.gisacl']
    return resources, library_raw, library, model


def validate_clip(name, raw, library, model):
    if name not in CLIPS:
        raise ValueError('only tutorial idle/fire are supported')
    expected = CLIPS[name]
    if sha(raw) != expected['wrapper_sha256']:
        raise ValueError('pinned tutorial clip wrapper SHA-256 mismatch')
    parsed = parse_clip(raw)
    acl = raw[parsed['acl_offset']:]
    if parsed['acl_sha256'] != expected['acl_sha256']:
        raise ValueError('pinned tutorial ACL SHA-256 mismatch')
    if f'{fnv32(acl[8:]):08x}' != parsed['acl_fnv32']:
        raise ValueError('ACL embedded FNV32 mismatch')
    if (parsed['bone_count'], parsed['samples'], parsed['sample_rate'], parsed['segments']) != (61, expected['samples'], expected['sample_rate'], expected['segments']):
        raise ValueError('pinned tutorial clip metadata mismatch')
    entry = library['clips'][expected['library_index']]
    if entry['name'] != name or entry['root_bone'] != 'root':
        raise ValueError('clip library record identity changed')
    parsed['library_record'] = entry
    parsed['bone_mapping'] = map_bones(library, parsed, [bone['name'] for bone in model['bones']])
    return parsed, acl


def decoder_provenance():
    provenance = json.loads(bounded(SAMPLER_ROOT/'provenance.json', 64*1024))
    if provenance['archiveSha256'] != ACL_SOURCE_SHA or file_sha256(SAMPLER_ROOT/'acl-v1.2.0.zip') != ACL_SOURCE_SHA:
        raise ValueError('official ACL source archive identity changed')
    if provenance['sourceUrl'] != 'https://codeload.github.com/nfrechette/acl/zip/refs/tags/v1.2.0':
        raise ValueError('unexpected ACL source origin')
    if provenance['wrapperSha256'] != WRAPPER_SHA or file_sha256(ROOT/'tools/acl_sample.cpp') != WRAPPER_SHA:
        raise ValueError('reviewed restricted decoder wrapper changed')
    if file_sha256(SAMPLER) != provenance['executableSha256']:
        raise ValueError('ACL executable differs from its recorded build')
    pins = {
        'stand_idle.acl': 'cda4d69e000276ee263a47d5531c43cbc6ae84ff6e133d64fbeeb7ccb7de898f',
        'skin.acl': '6bf93b1e7791dd6124a6e13c26538cfeac56d65c0d49abffc68a818c06be4cbd',
        **{f'tutorial_enemy_{name}.acl': data['acl_sha256'] for name, data in CLIPS.items()},
    }
    if provenance['acceptedInputSha256'] != pins:
        raise ValueError('decoder must retain exactly the four reviewed sample pins')
    return provenance


def reference_bind_comparison(library, model):
    reference = dict(zip(library['bone_names'], library['reference_pose']))
    rows = []
    for index, bone in enumerate(model['bones']):
        pose = reference[bone['name']]
        transform = np.eye(4)
        transform[:3, :3] = quaternion_matrix(pose[3:7])*pose[7:10]
        transform[:3, 3] = pose[:3]
        raw = np.asarray(matrix_rows(bone['matrix_raw']))
        parent = bone['parent']
        local = raw if parent is None else np.linalg.inv(np.asarray(matrix_rows(model['bones'][parent]['matrix_raw'])))@raw
        rows.append({'mesh_joint': index, 'name': bone['name'], 'parent': parent,
            'max_reference_vs_raw': float(np.max(np.abs(transform-raw))),
            'max_reference_vs_local': float(np.max(np.abs(transform-local))),
            'translation_reference': pose[:3], 'translation_raw': raw[:3, 3].tolist(),
            'translation_local': local[:3, 3].tolist()})
    return {'method': 'library T*R*S versus inverse(parent source matrix)*child source matrix; reference quaternions normalized only for comparison',
        'max_local_matrix_component_error': max(row['max_reference_vs_local'] for row in rows),
        'raw_matrices_or_samples_modified': False,
        'limitation': 'Supports relative matrix convention; does not validate auxiliary bounds or engine skinning.', 'rows': rows}


def motion_summary(raw, mapping):
    summary = summarize_poses(raw)
    frames, bones = summary['frames'], summary['bone_count']
    values = np.frombuffer(raw, dtype='<f4', offset=20).reshape(frames, bones, 10).astype(np.float64)
    translations = np.linalg.norm(values[:, :, 4:7]-values[0, :, 4:7], axis=2)
    scales = np.max(np.abs(values[:, :, 7:]-values[0, :, 7:]), axis=2)
    quaternions = values[:, :, :4]
    normalized = quaternions/np.linalg.norm(quaternions, axis=2, keepdims=True)
    dots = np.abs(np.sum(normalized*normalized[0], axis=2))
    rotations = np.degrees(2*np.arccos(np.clip(dots, -1, 1)))
    changes = []
    for index, row in enumerate(mapping):
        changes.append({**row,
            'max_translation_distance_from_first': float(np.max(translations[:, index])),
            'max_rotation_degrees_from_first': float(np.max(rotations[:, index])),
            'max_scale_component_change_from_first': float(np.max(scales[:, index]))})
    selected = sorted({0, (frames-1)//2, frames-1})
    frame_samples = [{'frame': index, 'source_time_seconds': index/summary['sample_rate'],
        'poses': [{'clip_index': row['clip_index'], 'mesh_joint': row['mesh_joint'], 'name': row['name'],
                   'quaternion_xyzw': values[index, i, :4].tolist(),
                   'translation_xyz': values[index, i, 4:7].tolist(),
                   'scale_xyz': values[index, i, 7:].tolist()} for i, row in enumerate(mapping)]} for index in selected]
    return {'source_local_samples_only': True,
        'moving_bones': sum(row['max_translation_distance_from_first'] > 1e-6 or row['max_rotation_degrees_from_first'] > 1e-4
                            or row['max_scale_component_change_from_first'] > 1e-6 for row in changes),
        'max_translation_distance_from_first': float(np.max(translations)),
        'max_rotation_degrees_from_first': float(np.max(rotations)),
        'max_scale_component_change_from_first': float(np.max(scales)),
        'first_last_max_translation_distance': float(np.max(translations[-1])),
        'first_last_max_rotation_degrees': float(np.max(rotations[-1])),
        'changes_by_bone': changes, 'frame_samples': frame_samples,
        'loop_correction_applied': False, 'coordinate_or_unit_conversion_applied': False}


def recover(apk, output=OUT):
    output = output.resolve()
    if output != OUT.resolve() and OUT.resolve() not in output.parents:
        raise ValueError('output must remain inside analysis/tutorial-enemy-animation')
    if file_sha256(apk) != APK_SHA:
        raise ValueError('original APK SHA-256 mismatch')
    resources, library_raw, library, model = inputs()
    decoder = decoder_provenance()
    output.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    (output/'library.gisacl').write_bytes(library_raw)
    save_json(output/'library.json', library)
    save_json(output/'decoder-build.json', decoder)
    bind = reference_bind_comparison(library, model)
    save_json(output/'reference-bind-comparison.json', bind)
    model_names = [bone['name'] for bone in model['bones']]
    save_json(output/'model-skeleton.json', {'sha256': MODEL_SHA, 'source': next(entry for entry in resources['entries'] if entry['output'] == 'enemy-model.mesh'),
        'bones': [{'mesh_joint': index, 'name': bone['name'], 'parent': bone['parent']} for index, bone in enumerate(model['bones'])]})
    reports = []
    for name, expected in CLIPS.items():
        logical = clip_path(LIBRARY_PATH, name)
        path = output/(name+'.gisacl')
        source = extract_with_provenance(apk, catalogue, logical, path, APK_SHA)
        if (source['member'], source['index'], source['npk_offset']) != ('assets/res/character.npk', expected['npk_index'], expected['offset']):
            raise ValueError('clip archive identity/offset changed')
        parsed, acl = validate_clip(name, bounded(path), library, model)
        parsed['source'] = source
        acl_path, pose_path = output/(name+'.acl'), output/(name+'.poses')
        acl_path.write_bytes(acl)
        sampled = sample_clip(SAMPLER, acl_path, pose_path, parsed)
        if sampled['sampler']['clipName'] != f'tutorial_enemy_{name}.acl' or sampled['sampler']['validationScope'] != 'sha256-pinned-original-clips-only':
            raise ValueError('wrong sampler allowlist receipt')
        parsed.update(sampled)
        parsed['sampler_executable_sha256'] = decoder['executableSha256']
        parsed['sampler_wrapper_sha256'] = WRAPPER_SHA
        motion = motion_summary(bounded(pose_path), parsed['bone_mapping'])
        parsed['motion_summary_file'] = name+'.motion.json'
        parsed['not_verified'] = ['engine playback', 'clip to skill timeline/event association', 'between-sample interpolation and looping', 'model skinning/auxiliary bounds']
        save_json(output/(name+'.json'), parsed)
        save_json(output/(name+'.motion.json'), motion)
        reports.append({'name': name, 'library_index': expected['library_index'], 'source': source,
            **{key: parsed[key] for key in ['acl_sha256', 'acl_fnv32', 'acl_hash_verified', 'bone_count', 'samples', 'sample_rate', 'duration_seconds']},
            'pose_sha256': parsed['poses']['sha256'], 'pose_bytes': parsed['poses']['bytes'],
            'max_quaternion_norm_squared_error': parsed['poses']['max_quaternion_norm_squared_error'],
            'moving_bones': motion['moving_bones'], 'max_translation_distance_from_first': motion['max_translation_distance_from_first'],
            'max_rotation_degrees_from_first': motion['max_rotation_degrees_from_first']})
    summary = {'kind': 'pinned-original-animation-data-sampling', 'apk_sha256': APK_SHA,
        'library_index': 6081, 'library_sha256': LIBRARY_SHA, 'library_path': LIBRARY_PATH,
        'model_sha256': MODEL_SHA, 'model_names': model_names, 'bone_count': 61,
        'decoder_build': decoder, 'clips': reports,
        'reference_to_mesh_local_max_error': bind['max_local_matrix_component_error'],
        'game_code_executed': False, 'engine_playback_verified': False,
        'evidence_kind': 'Custom static resource parsing plus execution of separately built official ACL data decoder; no new REA native Evidence.',
        'prior_reader_evidence': {'document': 'docs/animation-recovery.md', 'libclient_sha256': '54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef',
            'RGIS_reader': '0x993ee8..0x9945a4', 'clip_wrapper_reader': '0x98fe00..0x99028c',
            'StringIDMurmur3': '0x18eaf44', 'MurmurHash3A': '0x18eb5f4', 'seed': '0x9747b28c'},
        'tool_sha256': {file: file_sha256(ROOT/file) for file in ['tools/sample_tutorial_enemy_animation.py', 'tools/inspect_neox_animation.py',
            'tools/inspect_neox_model.py', 'tools/neox_resource_paths.py', 'tools/acl_sample.cpp']},
        'limitations': ['Clip names idle/fire do not establish a mapping to skills 990/991/992.',
            'Only original sample times are recovered; no target-engine interpolation, looping or visible pose acceptance.',
            '61-bone ID/name mapping does not by itself validate mesh auxiliary bounds or rendered skinning.']}
    save_json(output/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    parser.add_argument('--output', type=Path, default=OUT)
    result = recover(**vars(parser.parse_args()))
    print(json.dumps({key: result[key] for key in ['library_index', 'bone_count', 'clips', 'reference_to_mesh_local_max_error', 'engine_playback_verified']}, indent=2))
