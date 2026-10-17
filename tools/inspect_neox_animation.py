"""Bounded static readers for the observed NeoX RGIS/ACL wrappers.

The game is never loaded. Native reader offsets are documented in
docs/animation-recovery.md. ACL sampling is a separate, restricted helper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from inspect_neox_model import Reader, ModelError, extract_npk_entry, parse_model
from neox_resource_paths import lookup_logical, read_catalogue

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32 * 1024 * 1024
LIBRARY_PATH = 'character/player/ailisha/ailisha.gisacl'
MASK = 0xffffffff


def bone_id(name: str) -> int:
    """StringIDMurmur3: MurmurHash3 x86_32 with native seed 0x9747b28c."""
    if not isinstance(name, str) or not name or '\0' in name:
        raise ValueError('expected a nonempty bone name without NUL')
    data = name.encode('utf8')
    h = 0x9747b28c

    def rot(value, bits):
        return ((value << bits) | (value >> (32-bits))) & MASK

    def mix(value):
        return rot(value * 0xcc9e2d51 & MASK, 15) * 0x1b873593 & MASK

    end = len(data) // 4 * 4
    for offset in range(0, end, 4):
        h ^= mix(int.from_bytes(data[offset:offset+4], 'little'))
        h = (rot(h, 13) * 5 + 0xe6546b64) & MASK
    if data[end:]:
        h ^= mix(int.from_bytes(data[end:], 'little'))
    h ^= len(data)
    h ^= h >> 16
    h = h * 0x85ebca6b & MASK
    h ^= h >> 13
    h = h * 0xc2b2ae35 & MASK
    return h ^ (h >> 16)


def cstring(raw: bytes, *, allow_empty: bool = False) -> str:
    if b'\0' not in raw:
        raise ValueError('unterminated fixed-size name')
    result = raw.split(b'\0', 1)[0].decode('utf8', errors='strict')
    if not result and not allow_empty:
        raise ValueError('empty name')
    # Bytes after the first NUL are opaque padding and need not be zero.
    return result


def parse_library(data: bytes, *, allow_empty_roots: bool = False) -> dict:
    if len(data) > MAX_BYTES:
        raise ValueError('library exceeds input budget')
    r = Reader(data)
    magic, version, clips, bones = r.unpack('4sIHI', 'RGIS header')
    if magic != b'RGIS' or version != 0x03070000:
        raise ValueError('unsupported RGIS magic/version')
    if not 1 <= clips <= 4096 or not 1 <= bones <= 254:
        raise ValueError('RGIS counts outside supported bounds')
    names = [cstring(r.take(32, 'bone name')) for _ in range(bones)]
    if len(set(names)) != bones:
        raise ValueError('duplicate library bone names')
    reference_pose = r.vectors(bones, 10, 'reference TRS')
    for pose in reference_pose:
        if abs(sum(v*v for v in pose[3:7]) - 1) > 0.001:
            raise ValueError('reference quaternion is not unit length')
    separate, record_size = r.unpack('II', 'clip storage flags')
    if separate != 1 or record_size != 1108:
        raise ValueError('unsupported clip record layout')
    if r.pos + clips * record_size != len(data):
        raise ValueError('clip table does not exactly cover remaining payload')
    records = []
    for index in range(clips):
        offset = r.pos
        record = r.take(record_size, 'clip record')
        name = cstring(record[:32])
        root = cstring(record[32:64], allow_empty=allow_empty_roots)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('unsupported clip path component')
        # Native reader 0x9901d0 copies record+0x44c to BonesAnimData+0x48c.
        # Event-time consumers use milliseconds; see enemy-timing/loader-chain.json.
        duration_ms = struct.unpack_from('<f', record, 0x44c)[0]
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError('invalid clip duration')
        records.append({'index': index, 'name': name, 'root_bone': root,
                        'offset': offset, 'size': record_size,
                        'duration_ms': duration_ms, 'duration_field_offset': offset + 0x44c,
                        'opaque_tail_sha256': hashlib.sha256(record[64:]).hexdigest()})
    if len({r['name'] for r in records}) != clips:
        raise ValueError('duplicate clip names')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'version_hex': f'{version:08x}', 'bone_count': bones,
            'bone_names': names, 'reference_trs_order': 'translation xyz, quaternion xyzw, scale xyz',
            'reference_pose': reference_pose, 'clip_count': clips, 'clips': records,
            'coverage_bytes': r.pos, 'source_ranges': r.ranges}


def clip_path(library_path: str, name: str) -> str:
    if not library_path.endswith('.gisacl') or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('unsupported library/clip path')
    # Reader replaces the extension with _gis, then formats %s_acl/%s.gisacl.
    return library_path[:-7] + '_gis_acl/' + name + '.gisacl'


def parse_clip(data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise ValueError('clip exceeds input budget')
    r = Reader(data)
    bones = r.scalar('I', 'bone count')
    if not 1 <= bones <= 254:
        raise ValueError('clip bone count outside bounds')
    ids = r.unpack('I' * bones, 'bone IDs')
    if len(set(ids)) != bones:
        raise ValueError('duplicate clip bone IDs')
    unknown_a, unknown_b, size, checksum = r.unpack('4I', 'clip wrapper fields')
    acl_offset = r.pos
    if size < 48 or r.pos + size != len(data):
        raise ValueError('ACL length does not exactly cover remaining payload')
    acl = r.take(size, 'ACL buffer')
    declared, acl_checksum, tag, version, algorithm, padding = struct.unpack_from('<IIIHBB', acl)
    if declared != size or acl_checksum != checksum:
        raise ValueError('wrapper and ACL length/hash disagree')
    if tag != 0xac10ac10 or version != 4 or algorithm != 0 or padding != 0:
        raise ValueError('unsupported ACL tag/version/algorithm')
    acl_bones, segments = struct.unpack_from('<HH', acl, 16)
    samples, rate = struct.unpack_from('<If', acl, 28)
    if acl_bones != bones or not 1 <= samples <= 100000 or bones * samples > 2000000:
        raise ValueError('ACL sample/bone count outside supported bounds')
    if not 1 <= segments <= samples or not math.isfinite(rate) or not 0 < rate <= 1000:
        raise ValueError('invalid ACL segments/sample rate')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'bone_count': bones, 'bone_ids': list(ids),
            'unknown_wrapper_words': [f'{unknown_a:08x}', f'{unknown_b:08x}'],
            'acl_offset': acl_offset, 'acl_bytes': size,
            'acl_sha256': hashlib.sha256(acl).hexdigest(), 'acl_fnv32': f'{checksum:08x}',
            'acl_version': version, 'segments': segments, 'samples': samples,
            'sample_rate': rate, 'duration_seconds': (samples-1)/rate,
            'acl_hash_verified': False,
            'validation_scope': 'Wrapper/header only; full ACL validation belongs to the native sampler.',
            'source_ranges': r.ranges}


def map_bones(library: dict, clip: dict, model_names: list[str], *, allow_library_extras: bool = False) -> list[dict]:
    """Map clip tracks to mesh joints by library bone identity.

    With allow_library_extras, library/clip bones absent from the mesh (props,
    attachment chains) are left unmapped. The library stores no hierarchy, so
    this is only sound because mesh joints are posed through mesh parents.
    """
    if len(set(model_names)) != len(model_names):
        raise ValueError('duplicate model bone names')
    names = library['bone_names']
    hashes = [bone_id(name) for name in names]
    if len(set(hashes)) != len(hashes):
        raise ValueError('ambiguous bone hash collision')
    mesh_covered = set(names) >= set(model_names) if allow_library_extras else set(names) == set(model_names)
    if set(hashes) != set(clip['bone_ids']) or not mesh_covered:
        raise ValueError('clip/library/model skeleton identities differ')
    library_by_hash = {value: index for index, value in enumerate(hashes)}
    model_by_name = {name: index for index, name in enumerate(model_names)}
    result = []
    for index, value in enumerate(clip['bone_ids']):
        library_index = library_by_hash[value]
        name = names[library_index]
        if name not in model_by_name:
            continue
        result.append({'clip_index': index, 'bone_id': f'{value:08x}', 'name': name,
                       'library_index': library_index, 'mesh_joint': model_by_name[name]})
    return result


def summarize_poses(data: bytes) -> dict:
    if len(data) < 20 or len(data) > 80_000_020 or data[:8] != b'HCZPOSE1':
        raise ValueError('invalid sampled pose file')
    bones, frames, rate = struct.unpack_from('<IIf', data, 8)
    if not 1 <= bones <= 254 or not 1 <= frames <= 100000 or bones * frames > 2000000:
        raise ValueError('sampled pose counts outside budget')
    if not math.isfinite(rate) or not 0 < rate <= 1000 or len(data) != 20+bones*frames*40:
        raise ValueError('sampled pose length/rate invalid')
    first = []
    max_q_error = 0.0
    max_translation_change = 0.0
    scale_min, scale_max = math.inf, -math.inf
    for index, pose in enumerate(struct.iter_unpack('<10f', memoryview(data)[20:])):
        if not all(math.isfinite(v) for v in pose):
            raise ValueError('nonfinite sampled transform')
        error = abs(sum(v*v for v in pose[:4])-1)
        if error >= 0.001:
            raise ValueError('sampled quaternion is not unit length')
        max_q_error = max(max_q_error, error)
        if index < bones:
            first.append(pose)
        reference = first[index % bones]
        max_translation_change = max(max_translation_change,
                                     max(abs(pose[j]-reference[j]) for j in (4, 5, 6)))
        scale_min, scale_max = min(scale_min, *pose[7:]), max(scale_max, *pose[7:])
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'bone_count': bones, 'frames': frames, 'sample_rate': rate,
            'duration_seconds': (frames-1)/rate, 'first_frame': first,
            'transform_order': 'quaternion xyzw, translation xyz, scale xyz',
            'max_quaternion_norm_squared_error': max_q_error,
            'max_translation_component_change_from_first_frame': max_translation_change,
            'scale_range': [scale_min, scale_max]}


def save_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def file_sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def sample_clip(executable: Path, acl_path: Path, pose_path: Path, clip: dict) -> dict:
    # A fresh empty file cannot accidentally stand in for an earlier success.
    with tempfile.NamedTemporaryFile(dir=pose_path.parent, suffix='.poses.pending', delete=False) as output:
        pending = Path(output.name)
    try:
        sampled = subprocess.run([str(executable.resolve()), str(acl_path.resolve()), str(pending.resolve())],
                                 check=True, capture_output=True, text=True, timeout=120)
        metadata = json.loads(sampled.stdout)
        expected = {'aclVersion': '1.2.0', 'binaryVersion': 4, 'hashVerified': True,
                    'bones': clip['bone_count'], 'samples': clip['samples'],
                    'sampleRate': clip['sample_rate'], 'inputSha256': clip['acl_sha256']}
        if any(type(metadata.get(key)) is not type(value) and key != 'sampleRate'
               or metadata.get(key) != value for key, value in expected.items()):
            raise ValueError('sampler report does not match input identity/metadata')
        poses = summarize_poses(pending.read_bytes())
        if (poses['bone_count'], poses['frames'], poses['sample_rate']) != (
                clip['bone_count'], clip['samples'], clip['sample_rate']):
            raise ValueError('sampler pose metadata differs from wrapper')
        pending.replace(pose_path)
        return {'sampler': metadata, 'poses': poses, 'acl_hash_verified': True}
    finally:
        pending.unlink(missing_ok=True)


def extract_with_provenance(apk, catalogue, logical, output, apk_sha256):
    matches = lookup_logical(catalogue, logical)
    if len(matches) != 1:
        raise ValueError(f'expected unique resource path: {logical}, matches={len(matches)}')
    row = matches[0]
    source = extract_npk_entry(apk, row['member'], row['index'], output)
    source['logical_path'] = logical
    source['apk_sha256'] = apk_sha256
    # Include the original extension, so .ags and .gisacl never share a sidecar.
    save_json(Path(str(output)+'.source.json'), source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'analysis/animation/recovered')
    parser.add_argument('--model', type=Path, default=ROOT/'analysis/resource-mapping/elsa-yangcheng.mesh')
    parser.add_argument('--sampler', type=Path, help='Optional separately built ACL data sampler')
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    apk_sha256 = file_sha256(args.apk)
    catalogue = read_catalogue(args.apk)
    source = extract_with_provenance(args.apk, catalogue, LIBRARY_PATH, out/'ailisha.gisacl', apk_sha256)
    library = parse_library((out/'ailisha.gisacl').read_bytes())
    library['source'] = source
    save_json(out/'library.json', library)
    matches = [{'path': clip_path(LIBRARY_PATH, row['name']),
                'matches': lookup_logical(catalogue, clip_path(LIBRARY_PATH, row['name']))}
               for row in library['clips']]
    save_json(out/'clip-path-matches.json', matches)
    model = parse_model(args.model.read_bytes())
    reports = []
    for name in ('stand_idle', 'skin'):
        path = out/(name+'.gisacl')
        source = extract_with_provenance(args.apk, catalogue, clip_path(LIBRARY_PATH, name), path, apk_sha256)
        raw = path.read_bytes()
        clip = parse_clip(raw)
        clip['source'] = source
        clip['bone_mapping'] = map_bones(library, clip, [b['name'] for b in model['bones']])
        acl_path = out/(name+'.acl')
        acl_path.write_bytes(raw[clip['acl_offset']:])
        if args.sampler:
            clip.update(sample_clip(args.sampler, acl_path, out/(name+'.poses'), clip))
            clip['sampler_executable_sha256'] = file_sha256(args.sampler)
        save_json(out/(name+'.json'), clip)
        reports.append({k: clip[k] for k in ('bone_count', 'samples', 'sample_rate', 'duration_seconds',
                                            'acl_sha256', 'acl_hash_verified')} | {'name': name})
    summary = {'apk_sha256': apk_sha256, 'library': LIBRARY_PATH, 'library_sha256': library['sha256'],
               'bone_count': library['bone_count'], 'clip_count': library['clip_count'],
               'uniquely_located_clips': sum(len(row['matches']) == 1 for row in matches),
               'model_sha256': model['sha256'], 'clips': reports,
               'limitations': ['Clip record tails and two wrapper words remain opaque.',
                   'Bone identity and sampled pose recovery are not proof of correct on-screen playback.',
                   'Reference-pose/bind differences must be retained and investigated.']}
    save_json(out/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
