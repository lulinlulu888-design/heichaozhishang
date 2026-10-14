"""Bounded, data-only NeoX 5.0.2/5.0.3 mesh inspection.

Schema corroborated with APK libclient.so Thumb readers/writers at
0xc21890, 0xc21998, 0xc21d9c, 0xc22878, 0xc22cec; see docs/model-conversion.md.
No target code is executed. Unsupported variants fail rather than guess.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
import zipfile
from pathlib import Path

MAGIC = 0xBBC88034
MAX_BYTES = 32 * 1024 * 1024


class ModelError(ValueError):
    pass


def extract_npk_entry(apk: Path, member: str, index: int, output: Path):
    """Read exactly one bounded entry, preserving its archive/table provenance."""
    from extract_npk import decode_entry
    with zipfile.ZipFile(apk) as z, z.open(member) as f:
        magic, count, r1, r2, version, table = struct.unpack('<4s5I', f.read(24))
        size = z.getinfo(member).file_size
        if magic != b'NXPK' or version != 1 or count > 100000 or not 0 <= index < count:
            raise ModelError('unsupported NPK header or index')
        if table < 24 or table+count*28 != size:
            raise ModelError('invalid NPK table bounds')
        f.seek(table+index*28)
        row = struct.unpack('<6I2H', f.read(28))
        if row[1] < 24 or row[1]+row[2] > table or row[2] > MAX_BYTES or row[3] > MAX_BYTES:
            raise ModelError('NPK entry out of bounds or exceeds budget')
        f.seek(row[1])
        stored = f.read(row[2])
    entry = dict(zip(('name_hash', 'offset', 'stored_size', 'original_size', 'digest1', 'digest2', 'compression', 'encryption'), row))
    entry['offset'] = 0
    data = decode_entry(stored, entry, max_decoded_bytes=MAX_BYTES)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    source = {'apk': str(apk.resolve()), 'member': member, 'index': index,
              'name_hash': f'{row[0]:08x}', 'npk_offset': row[1], 'stored_size': row[2],
              'decoded_size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'table_row': row}
    output.with_suffix('.source.json').write_text(json.dumps(source, indent=2), encoding='utf8')
    return source


class Reader:
    def __init__(self, data: bytes):
        self.data, self.pos, self.ranges = data, 0, []

    def take(self, n: int, name: str) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ModelError(f'{name}: range outside payload at 0x{self.pos:x}, size {n}')
        start = self.pos
        self.pos += n
        self.ranges.append({'name': name, 'offset': start, 'size': n})
        return self.data[start:self.pos]

    def unpack(self, fmt: str, name: str):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt), name))

    def scalar(self, fmt: str, name: str):
        return self.unpack(fmt, name)[0]

    def vectors(self, count: int, width: int, name: str):
        raw = self.take(count * width * 4, name)
        vals = list(struct.iter_unpack('<' + 'f' * width, raw))
        if not all(math.isfinite(v) for row in vals for v in row):
            raise ModelError(f'{name}: nonfinite float')
        return vals


def det3(m):
    return (m[0]*(m[5]*m[10]-m[6]*m[9]) -
            m[1]*(m[4]*m[10]-m[6]*m[8]) +
            m[2]*(m[4]*m[9]-m[5]*m[8]))


def matrix_rows(column_major):
    return [[column_major[c*4+r] for c in range(4)] for r in range(4)]


def inverse4(m):
    a = [list(row) + [float(i == j) for j in range(4)] for i, row in enumerate(m)]
    for i in range(4):
        pivot = max(range(i, 4), key=lambda j: abs(a[j][i]))
        if abs(a[pivot][i]) < 1e-12:
            raise ModelError('singular matrix')
        a[i], a[pivot] = a[pivot], a[i]
        p = a[i][i]
        a[i] = [v / p for v in a[i]]
        for j in range(4):
            if j != i:
                p = a[j][i]
                a[j] = [v - p*w for v, w in zip(a[j], a[i])]
    return [row[4:] for row in a]


def multiply4(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def validate_bind_pose(model, tolerance=1e-4):
    """Cross-check transform direction with independently stored per-bone AABBs.

    Inverse model-space bone matrices must turn influenced mesh vertices into
    exactly the local bounds recorded in the 28-byte auxiliary blocks. This is
    an evidence check, not the tautological M*inverse(M) rest-pose check.
    """
    if not model['bones']:
        return {'validated': False, 'reason': 'no skeleton'}
    local = {i: [] for i in model['used_bones']}
    inv = [inverse4(matrix_rows(b['matrix_raw'])) for b in model['bones']]
    for p, js, ws in zip(model['positions'], model['joints'], model['weights']):
        v = (*p, 1.0)
        for j in {j for j, w in zip(js, ws) if w > 0}:
            local[j].append([sum(inv[j][a][k]*v[k] for k in range(4)) for a in range(3)])
    rows = []
    for i, vertices in local.items():
        bound = model['bones'][i]['auxiliary_unknown']
        if bound is None or any(x < 0 for x in bound[3:7]):
            raise ModelError('missing or invalid auxiliary bounds; bind pose role unverified')
        error = max(abs(min(v[a] for v in vertices)-(bound[a]-bound[a+3])) for a in range(3))
        error = max(error, max(abs(max(v[a] for v in vertices)-(bound[a]+bound[a+3])) for a in range(3)))
        radius_error = abs(math.sqrt(sum(v*v for v in bound[3:6]))-bound[6])
        if max(error, radius_error) > tolerance:
            raise ModelError(f'bone {i}: independent bind-pose bounds check failed: {error}, {radius_error}')
        rows.append({'bone': i, 'name': model['bones'][i]['name'], 'influenced_vertices': len(vertices),
                     'bound_error': error, 'radius_error': radius_error})
    return {'validated': True, 'method': 'inverse(raw bone matrix) maps influenced model vertices to recorded local AABB',
            'tolerance': tolerance, 'rows': rows,
            'max_bound_error': max(x['bound_error'] for x in rows),
            'max_radius_error': max(x['radius_error'] for x in rows)}


def parse_model(data: bytes, subset_count: int | None = None, *, preserve_nonunit_normals: bool = False):
    if len(data) > MAX_BYTES:
        raise ModelError('payload exceeds 32 MiB investigation budget')
    r = Reader(data)
    magic, version, kind = r.unpack('IIH', 'header')
    if magic != MAGIC or version not in (0x50002, 0x50003) or kind not in (0, 1):
        raise ModelError(f'unsupported magic/version/precision/type: {magic:x}/{version:x}/{kind}')
    if r.take(2, 'optional_animation_flags') != b'\0\0':
        raise ModelError('optional animation blocks are not implemented')
    bones = []
    if kind == 1:
        n = r.scalar('H', 'bone_count')
        if not 1 <= n <= 254:
            raise ModelError('bone count outside native reader supported 1..254')
        parents = r.take(n, 'bone_parent_indices')
        names_raw = r.take(n * 32, 'bone_names')
        names = []
        for i in range(n):
            raw = names_raw[i*32:(i+1)*32]
            if b'\0' not in raw:
                raise ModelError('unterminated bone name')
            names.append(raw.split(b'\0', 1)[0].decode('utf-8', errors='strict'))
        for i in range(n):
            seen, j = set(), i
            while j != 255:
                if j >= n or j in seen:
                    raise ModelError('bone parent out of bounds or cyclic')
                seen.add(j)
                j = parents[j]
        flag = r.scalar('B', 'bone_auxiliary_present')
        if flag not in (0, 1):
            raise ModelError('invalid bone auxiliary flag')
        auxiliary = r.vectors(n, 7, 'bone_auxiliary_28B_unknown') if flag else [None] * n
        matrices = r.vectors(n, 16, 'bone_matrices_64B')
        for i, m in enumerate(matrices):
            if max(abs(m[k]) for k in (3, 7, 11)) > 1e-5 or abs(m[15] - 1) > 1e-5:
                raise ModelError(f'bone {i}: nonaffine matrix')
            if abs(det3(m)) < 1e-10:
                raise ModelError(f'bone {i}: singular matrix')
            bones.append({'name': names[i], 'parent': None if parents[i] == 255 else parents[i],
                          'matrix_raw': m, 'auxiliary_unknown': auxiliary[i]})
        if r.scalar('B', 'extra_skeletal_data_present') != 0:
            raise ModelError('extra skeletal data not implemented')
    directory_ptr = r.scalar('I', 'directory_offset')
    geometry_start = r.pos
    if directory_ptr < geometry_start or directory_ptr + 16 != len(data):
        raise ModelError('only a single geometry directory record is supported')
    # This restricted directory shape is independently corroborated by c22cec.
    directory = struct.unpack_from('<HIHIHH', data, directory_ptr)
    if directory != (1, geometry_start, 1, 4, 0, 0):
        raise ModelError(f'unsupported directory shape: {directory}')
    # Native receives subset count from the containing model/material metadata.
    # Recover only a UNIQUE candidate satisfying totals and every byte boundary.
    candidates = []
    for count in ([subset_count] if subset_count is not None else range(1, 1025)):
        p = geometry_start + 10 * count
        if count < 1 or p + 10 > directory_ptr:
            continue
        marker, vertices, triangles = struct.unpack_from('<HII', data, p)
        if marker != 1 or not 1 <= vertices <= 1_000_000 or not 1 <= triangles <= 2_000_000:
            continue
        descriptors = [struct.unpack_from('<IIBB', data, geometry_start+i*10) for i in range(count)]
        if any(v == 0 or t == 0 or uv > 4 or col > 1 for v, t, uv, col in descriptors):
            continue
        if sum(d[0] for d in descriptors) != vertices or sum(d[1] for d in descriptors) != triangles:
            continue
        extras_at = p + 10 + vertices * 24
        if extras_at + 2 > directory_ptr:
            continue
        extra = struct.unpack_from('<H', data, extras_at)[0]
        end = extras_at + 2 + vertices * 12 * extra + triangles * 6
        end += sum(v * (uv * 8 + col * 4) for v, t, uv, col in descriptors)
        end += (vertices * 20 + 32) if kind == 1 else 0
        if extra in (0, 1) and end == directory_ptr:
            candidates.append((count, descriptors))
    if len(candidates) != 1:
        raise ModelError(f'expected one geometry descriptor count, found {len(candidates)}')
    count, descriptors = candidates[0]
    r.take(count*10, 'submesh_descriptors')
    marker, nv, nt = r.unpack('HII', 'geometry_header')
    positions = r.vectors(nv, 3, 'positions_float32')
    normals = r.vectors(nv, 3, 'normals_float32')
    norms = [math.sqrt(sum(x*x for x in v)) for v in normals]
    if preserve_nonunit_normals and any(n < 1e-8 for n in norms):
        raise ModelError('zero-length normal cannot be preserved as a direction')
    if not preserve_nonunit_normals and any(abs(n-1) > 0.01 for n in norms):
        raise ModelError('normal length differs from unit by more than 0.01')
    auxiliary_present = r.scalar('H', 'vertex_auxiliary_present')
    vertex_auxiliary = r.vectors(nv, 3, 'vertex_auxiliary_float3_unknown') if auxiliary_present else None
    indices = list(r.unpack(f'{nt*3}H', 'triangle_indices_uint16'))
    subsets = []
    vo = io = 0
    for v, t, u, c in descriptors:
        part = indices[io:io+t*3]
        if any(not vo <= idx < vo+v for idx in part):
            raise ModelError('triangle index outside its submesh vertex range')
        subsets.append({'vertex_start': vo, 'vertex_count': v, 'triangle_start': io//3,
                        'triangle_count': t, 'uv_count': u, 'color_present': bool(c), 'uvs': []})
        vo += v
        io += t*3
    for i, s in enumerate(subsets):
        for channel in range(s['uv_count']):
            s['uvs'].append(r.vectors(s['vertex_count'], 2, f'submesh_{i}_uv_{channel}'))
    for i, s in enumerate(subsets):
        s['colors_raw_hex'] = r.take(s['vertex_count']*4, f'submesh_{i}_colors_unknown').hex() if s['color_present'] else None
    joints = weights = None
    max_weight_error = 0.0
    used_bones = set()
    if kind == 1:
        joints = list(struct.iter_unpack('<4B', r.take(nv*4, 'joint_indices_uint8')))
        weights = r.vectors(nv, 4, 'joint_weights_float32')
        for js, ws in zip(joints, weights):
            if any(w < 0 or w > 1 for w in ws):
                raise ModelError('skin weight outside 0..1')
            error = abs(sum(ws) - 1)
            max_weight_error = max(max_weight_error, error)
            if error > 1e-4:
                raise ModelError('skin weights do not sum to one')
            for j, w in zip(js, ws):
                if j == 255 and w != 0 or j != 255 and j >= len(bones):
                    raise ModelError('skin bone index outside skeleton')
                if w:
                    used_bones.add(j)
        bitset = r.take(32, 'used_bones_bitset')
        recorded = {i for i in range(256) if bitset[i//8] & (1 << (i%8))}
        if used_bones != recorded:
            raise ModelError('used-bone bitset does not match vertex weights')
    if r.pos != directory_ptr:
        raise ModelError('geometry does not end at directory offset')
    r.take(16, 'directory')
    bbox = {'min': [min(p[j] for p in positions) for j in range(3)],
            'max': [max(p[j] for p in positions) for j in range(3)]}
    return {'format': 'NeoX mesh', 'version': hex(version), 'kind': kind,
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'coverage_bytes': r.pos, 'vertex_count': nv, 'triangle_count': nt,
            'submesh_count': count, 'subset_count_recovery': 'unique totals/length solution',
            'geometry_offset': geometry_start, 'directory_offset': directory_ptr,
            'positions': positions, 'normals': normals, 'indices': indices,
            'vertex_auxiliary_unknown': vertex_auxiliary, 'submeshes': subsets,
            'bones': bones, 'joints': joints, 'weights': weights,
            'used_bones': sorted(used_bones), 'bounds': bbox,
            'normal_length_range': [min(norms), max(norms)],
            'normal_policy': 'preserved source nonzero vectors' if preserve_nonunit_normals else 'unit within 0.01',
            'max_weight_sum_error': max_weight_error, 'ranges': r.ranges,
            'limitations': ['Bind matrix and 28B local-bound roles require validate_bind_pose for each skinned export.',
                            'Float3 vertex auxiliary semantics are not yet confirmed.',
                            'Material identities, textures and animation require companion assets.']}


def summary(model):
    omitted = {'positions', 'normals', 'indices', 'joints', 'weights', 'vertex_auxiliary_unknown'}
    result = {k: v for k, v in model.items() if k not in omitted}
    result['submeshes'] = [{k: v for k, v in s.items() if k not in ('uvs', 'colors_raw_hex')} for s in model['submeshes']]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--subset-count', type=int)
    ap.add_argument('--extract-index', type=int, help='Treat input as APK and extract this single NPK entry to output')
    ap.add_argument('--npk-member', default='assets/res/character.npk')
    args = ap.parse_args()
    if args.extract_index is not None:
        print(json.dumps(extract_npk_entry(args.input, args.npk_member, args.extract_index, args.output), indent=2))
        return
    if args.input.stat().st_size > MAX_BYTES:
        raise ModelError('input exceeds budget')
    result = summary(parse_model(args.input.read_bytes(), args.subset_count))
    result['input'] = str(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('sha256', 'vertex_count', 'triangle_count', 'submesh_count', 'coverage_bytes')}, indent=2))


if __name__ == '__main__':
    main()
