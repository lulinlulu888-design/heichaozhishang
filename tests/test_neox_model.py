"""Adversarial parsing checks and independent GLB roundtrip over real samples."""
import json
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from inspect_neox_model import ModelError, parse_model, validate_bind_pose, matrix_rows, multiply4
from export_neox_gltf import encode_glb

PLANE = ROOT / 'analysis/assets/portability/ui_model.00010.binary_3480c8bb.bin'
HERO = ROOT / 'analysis/model-conversion/character.06424.mesh'


def decode_glb(payload):
    magic, version, size = struct.unpack_from('<III', payload)
    assert (magic, version, size) == (0x46546c67, 2, len(payload))
    length, typ = struct.unpack_from('<II', payload, 12)
    assert typ == 0x4e4f534a and length % 4 == 0
    doc = json.loads(payload[20:20+length])
    length2, typ2 = struct.unpack_from('<II', payload, 20+length)
    assert typ2 == 0x004e4942 and length2 % 4 == 0
    data = payload[28+length:]
    assert len(data) == length2
    return doc, data


def read_accessor(doc, data, index):
    a = doc['accessors'][index]
    v = doc['bufferViews'][a['bufferView']]
    fmt = {5126: 'f', 5123: 'H', 5121: 'B'}[a['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    record = struct.Struct('<' + fmt * width)
    offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    assert offset % 4 == 0
    assert offset + record.size * a['count'] <= v['byteOffset'] + v['byteLength'] <= len(data)
    return [record.unpack_from(data, offset+i*record.size) for i in range(a['count'])]


@unittest.skipUnless(PLANE.exists(), 'real APK plane fixture not extracted')
class ModelParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plane = PLANE.read_bytes()

    def test_real_plane_exact_coverage(self):
        m = parse_model(self.plane)
        self.assertEqual((m['vertex_count'], m['triangle_count'], m['coverage_bytes']), (4, 2, 194))
        self.assertEqual(m['bounds']['min'][0], -96)
        self.assertEqual(m['bounds']['max'][1], 54)

    def test_all_truncations_fail(self):
        for i in range(len(self.plane)):
            with self.subTest(length=i), self.assertRaises(ModelError):
                parse_model(self.plane[:i])

    def test_explicit_nonunit_normal_preservation(self):
        original = parse_model(self.plane)
        # This fixed plane has four float3 positions starting at 0x24,
        # followed by four float3 normals. Keep all other structure unchanged.
        payload = bytearray(self.plane)
        expected = []
        for i, normal in enumerate(original['normals']):
            struct.pack_into('<3f', payload, 0x54+i*12, *(v*0.4 for v in normal))
            expected.append(struct.unpack_from('<3f', payload, 0x54+i*12))
        with self.assertRaisesRegex(ModelError, 'normal length'):
            parse_model(payload)
        preserved = parse_model(payload, preserve_nonunit_normals=True)
        self.assertEqual([tuple(n) for n in preserved['normals']], expected)
        self.assertEqual(preserved['positions'], original['positions'])
        self.assertEqual(preserved['coverage_bytes'], len(payload))
        struct.pack_into('<3f', payload, 0x54, 0, 0, 0)
        with self.assertRaisesRegex(ModelError, 'zero-length normal'):
            parse_model(payload, preserve_nonunit_normals=True)

    def test_index_out_of_range(self):
        b = bytearray(self.plane)
        struct.pack_into('<H', b, 0x86, 65535)
        with self.assertRaisesRegex(ModelError, 'index outside'):
            parse_model(b)

    def test_nonfinite_position(self):
        b = bytearray(self.plane)
        struct.pack_into('<f', b, 0x24, float('nan'))
        with self.assertRaisesRegex(ModelError, 'nonfinite'):
            parse_model(b)

    def test_impossible_count(self):
        b = bytearray(self.plane)
        struct.pack_into('<I', b, 0x1c, 0xffffffff)
        with self.assertRaises(ModelError):
            parse_model(b)

    def test_invalid_directory(self):
        for pos in (12, 180, 190):
            b = bytearray(self.plane)
            b[pos] ^= 64
            with self.subTest(offset=pos), self.assertRaises(ModelError):
                parse_model(b)

    def test_unsupported_precision_and_animation(self):
        for pos in (7, 10, 11):
            b = bytearray(self.plane)
            b[pos] = 1
            with self.subTest(offset=pos), self.assertRaises(ModelError):
                parse_model(b)

    def test_static_glb_arrays_exact(self):
        m = parse_model(self.plane)
        payload, _, _ = encode_glb(m)
        doc, b = decode_glb(payload)
        p = doc['meshes'][0]['primitives'][0]
        self.assertEqual(read_accessor(doc, b, p['attributes']['POSITION']), m['positions'])
        self.assertEqual(read_accessor(doc, b, p['attributes']['NORMAL']), m['normals'])
        self.assertEqual([x[0] for x in read_accessor(doc, b, p['indices'])], m['indices'])


@unittest.skipUnless(HERO.exists(), 'real APK hero fixture not extracted')
class RealSkinnedMeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = HERO.read_bytes()
        cls.model = parse_model(cls.payload)

    def test_real_model_counts_and_independent_bind_bounds(self):
        m = self.model
        self.assertEqual((m['vertex_count'], m['triangle_count'], m['submesh_count'], len(m['bones'])), (20268, 28864, 9, 159))
        self.assertEqual(m['coverage_bytes'], len(self.payload))
        self.assertLess(validate_bind_pose(m)['max_bound_error'], 3e-6)

    def test_parent_cycle_rejected(self):
        b = bytearray(self.payload)
        b[14] = 0
        with self.assertRaisesRegex(ModelError, 'cyclic'):
            parse_model(b)

    def test_out_of_range_influence_rejected(self):
        off = next(x['offset'] for x in self.model['ranges'] if x['name'] == 'joint_indices_uint8')
        b = bytearray(self.payload)
        b[off] = 254
        with self.assertRaisesRegex(ModelError, 'bone index'):
            parse_model(b)

    def test_zero_skin_weights_rejected(self):
        off = next(x['offset'] for x in self.model['ranges'] if x['name'] == 'joint_weights_float32')
        b = bytearray(self.payload)
        b[off:off+16] = bytes(16)
        with self.assertRaisesRegex(ModelError, 'sum to one'):
            parse_model(b)

    def test_wrong_bone_transform_fails_independent_check(self):
        m = dict(self.model)
        m['bones'] = [dict(b) for b in m['bones']]
        i = m['used_bones'][0]
        mat = list(m['bones'][i]['matrix_raw'])
        mat[12] += 0.1
        m['bones'][i]['matrix_raw'] = mat
        with self.assertRaisesRegex(ModelError, 'bind-pose bounds check failed'):
            validate_bind_pose(m)

    def test_glb_skin_rest_pose_and_geometry_roundtrip(self):
        m = self.model
        glb, _, _ = encode_glb(m, skin=True)
        d, b = decode_glb(glb)
        nodes, skin = d['nodes'], d['skins'][0]
        parents = {ch: i for i, node in enumerate(nodes) for ch in node.get('children', [])}
        identity = [[float(i == j) for j in range(4)] for i in range(4)]
        worlds = {}
        def world(i):
            if i not in worlds:
                local = matrix_rows(nodes[i]['matrix']) if 'matrix' in nodes[i] else identity
                worlds[i] = multiply4(world(parents[i]), local) if i in parents else local
            return worlds[i]
        ibms = read_accessor(d, b, skin['inverseBindMatrices'])
        skin_matrices = [multiply4(world(node), matrix_rows(ibms[i])) for i, node in enumerate(skin['joints'])]
        max_rest_error = 0.0
        for sub, primitive in zip(m['submeshes'], d['meshes'][0]['primitives']):
            attrs = primitive['attributes']
            positions = read_accessor(d, b, attrs['POSITION'])
            self.assertEqual(positions, m['positions'][sub['vertex_start']:sub['vertex_start']+sub['vertex_count']])
            indices = [r[0] + sub['vertex_start'] for r in read_accessor(d, b, primitive['indices'])]
            first = sub['triangle_start'] * 3
            self.assertEqual(indices, m['indices'][first:first+sub['triangle_count']*3])
            for p, js, ws in zip(positions, read_accessor(d, b, attrs['JOINTS_0']), read_accessor(d, b, attrs['WEIGHTS_0'])):
                v = (*p, 1)
                posed = [sum(w * sum(skin_matrices[j][row][k]*v[k] for k in range(4)) for j, w in zip(js, ws)) for row in range(3)]
                max_rest_error = max(max_rest_error, max(abs(x-y) for x, y in zip(p, posed)))
        self.assertLess(max_rest_error, 3e-6)


if __name__ == '__main__':
    unittest.main()
