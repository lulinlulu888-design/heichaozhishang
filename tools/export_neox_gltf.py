"""Export verified NeoX mesh arrays to glTF 2.0 GLB without target execution.

Standard: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
Default is static geometry; --skin requires the independent local-bounds check.
No textures, guessed materials, unit conversion or authored animation are added.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from inspect_neox_model import (MAX_BYTES, ModelError, inverse4, matrix_rows,
                                multiply4, parse_model, validate_bind_pose)


def flatten_columns(m):
    return [m[r][c] for c in range(4) for r in range(4)]


def encode_glb(model, name='NeoX extracted mesh', skin=False):
    binary = bytearray()
    doc = {'asset': {'version': '2.0', 'generator': 'hczs evidence-based NeoX converter'},
           'buffers': [], 'bufferViews': [], 'accessors': [],
           'meshes': [{'name': name, 'primitives': []}],
           'nodes': [{'name': name, 'mesh': 0}], 'scenes': [{'nodes': [0]}], 'scene': 0,
           'extras': {'sourceSha256': model['sha256'], 'sourceBytes': model['size'],
                      'sourceCoverageBytes': model['coverage_bytes'],
                      'coordinatePolicy': 'Original XYZ coordinates and unit scale preserved; real-world units unresolved.',
                      'missing': ['textures', 'material names and shading', 'animation clips'],
                      'triangleWinding': 'Source winding preserved; no sign or coordinate conversion.'}}

    def accessor(rows, width, fmt='f', target=34962, bounds=False):
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        pack = struct.Struct('<' + fmt*width)
        for row in rows:
            binary.extend(pack.pack(*(row if isinstance(row, (tuple, list)) else (row,))))
        view = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary)-offset}
        if target is not None:
            view['target'] = target
        doc['bufferViews'].append(view)
        a = {'bufferView': len(doc['bufferViews'])-1, 'componentType': {'f': 5126, 'H': 5123, 'B': 5121}[fmt],
             'count': len(rows), 'type': {1: 'SCALAR', 2: 'VEC2', 3: 'VEC3', 4: 'VEC4', 16: 'MAT4'}[width]}
        if bounds:
            a['min'] = [min(row[i] for row in rows) for i in range(width)]
            a['max'] = [max(row[i] for row in rows) for i in range(width)]
        doc['accessors'].append(a)
        return len(doc['accessors'])-1

    bind_report = None
    if skin:
        bind_report = validate_bind_pose(model)
        if not bind_report['validated']:
            raise ModelError('cannot export skin without verified bind matrices')
        matrices = [matrix_rows(b['matrix_raw']) for b in model['bones']]
        inverses = [inverse4(m) for m in matrices]
        roots = []
        max_orthogonality_error = 0.0
        for i, bone in enumerate(model['bones']):
            parent = bone['parent']
            local = matrices[i] if parent is None else multiply4(inverses[parent], matrices[i])
            # glTF node matrices must be decomposable to TRS, i.e. no shear.
            columns = [[local[r][c] for r in range(3)] for c in range(3)]
            norms = [math.sqrt(sum(x*x for x in col)) for col in columns]
            error = max(abs(sum(columns[a][k]*columns[b][k] for k in range(3))/(norms[a]*norms[b]))
                        for a, b in ((0, 1), (0, 2), (1, 2)))
            max_orthogonality_error = max(error, max_orthogonality_error)
            if error > 1e-4:
                raise ModelError('bone local transform has unsupported shear')
            node = {'name': bone['name'], 'matrix': flatten_columns(local)}
            children = [j+1 for j, b in enumerate(model['bones']) if b['parent'] == i]
            if children:
                node['children'] = children
            doc['nodes'].append(node)
            if parent is None:
                roots.append(i+1)
        # A common identity root makes every joint a descendant of skeleton.
        skeleton_root = len(doc['nodes'])
        doc['nodes'].append({'name': 'NeoX skeleton roots', 'children': roots})
        doc['scenes'][0]['nodes'].append(skeleton_root)
        ibm = accessor([flatten_columns(m) for m in inverses], 16, target=None)
        doc['skins'] = [{'name': name + ' bind skeleton', 'inverseBindMatrices': ibm,
                         'joints': list(range(1, len(model['bones'])+1)), 'skeleton': skeleton_root}]
        doc['nodes'][0]['skin'] = 0
        doc['extras']['bindPoseEvidence'] = {k: v for k, v in bind_report.items() if k != 'rows'}
        doc['extras']['localMatrixMaxOrthogonalityError'] = max_orthogonality_error
    for s in model['submeshes']:
        start, count = s['vertex_start'], s['vertex_count']
        stop = start + count
        attrs = {'POSITION': accessor(model['positions'][start:stop], 3, bounds=True),
                 'NORMAL': accessor(model['normals'][start:stop], 3)}
        for i, uv in enumerate(s['uvs']):
            attrs[f'TEXCOORD_{i}'] = accessor(uv, 2)
        if skin:
            # NeoX uses 255 for inactive influence, glTF requires an actual joint index.
            attrs['JOINTS_0'] = accessor([tuple(0 if j == 255 else j for j in row) for row in model['joints'][start:stop]], 4, 'B')
            weights = [tuple(w/sum(row) for w in row) for row in model['weights'][start:stop]]
            attrs['WEIGHTS_0'] = accessor(weights, 4)
        face_start = s['triangle_start']*3
        ix = [idx-start for idx in model['indices'][face_start:face_start+s['triangle_count']*3]]
        prim = {'attributes': attrs, 'indices': accessor(ix, 1, 'H', target=34963), 'mode': 4,
                'extras': {'sourceVertexStart': start, 'sourceTriangleStart': s['triangle_start']}}
        doc['meshes'][0]['primitives'].append(prim)
    doc['buffers'] = [{'byteLength': len(binary)}]
    json_bytes = json.dumps(doc, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    json_bytes += b' ' * (-len(json_bytes) % 4)
    binary.extend(b'\0' * (-len(binary) % 4))
    size = 12 + 8 + len(json_bytes) + 8 + len(binary)
    result = struct.pack('<III', 0x46546C67, 2, size)
    result += struct.pack('<II', len(json_bytes), 0x4E4F534A) + json_bytes
    result += struct.pack('<II', len(binary), 0x004E4942) + binary
    return result, doc, bind_report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--skin', action='store_true')
    args = ap.parse_args()
    if args.input.stat().st_size > MAX_BYTES:
        raise ModelError('input exceeds budget')
    model = parse_model(args.input.read_bytes())
    glb, doc, bind = encode_glb(model, args.input.stem, args.skin)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(glb)
    report = {'input': str(args.input.resolve()), 'source_sha256': model['sha256'],
              'output': str(args.output.resolve()), 'glb_sha256': hashlib.sha256(glb).hexdigest(),
              'glb_bytes': len(glb), 'vertex_count': model['vertex_count'], 'triangle_count': model['triangle_count'],
              'submesh_count': model['submesh_count'], 'skin': args.skin, 'bind_validation': bind,
              'source_ranges': model['ranges'], 'limitations': doc['extras']}
    args.output.with_suffix('.export.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('bind_validation', 'source_ranges', 'limitations')}, indent=2))


if __name__ == '__main__':
    main()
