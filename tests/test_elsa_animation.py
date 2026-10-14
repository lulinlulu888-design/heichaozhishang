"""Independent binary roundtrip and source-pose checks for Elsa animation GLB."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from export_elsa_animation import (continuous_quaternions, decompose_bind,
                                   load_clip, read_bounded)
from inspect_neox_animation import parse_library

OUT = ROOT/'analysis/elsa-animation'
RECOVERED = ROOT/'analysis/animation/recovered'


def glb_read(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data)
    assert (magic, version, length) == (0x46546c67, 2, len(data))
    json_size, typ = struct.unpack_from('<II', data, 12)
    assert typ == 0x4e4f534a
    doc = json.loads(data[20:20+json_size])
    size, typ = struct.unpack_from('<II', data, 20+json_size)
    assert typ == 0x004e4942 and 28+json_size+size == len(data)
    return doc, data[28+json_size:]


def read_accessor(doc, binary, ix):
    a = doc['accessors'][ix]
    view = doc['bufferViews'][a['bufferView']]
    width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    fmt = {5121: 'B', 5123: 'H', 5126: 'f'}[a['componentType']]
    record = struct.Struct('<'+fmt*width)
    start = view.get('byteOffset', 0)+a.get('byteOffset', 0)
    end = start+record.size*a['count']
    assert start % 4 == 0 and end <= view.get('byteOffset', 0)+view['byteLength'] <= len(binary)
    return np.array(list(record.iter_unpack(binary[start:end])))


def trs_matrix(t, q, scale):
    # Rodrigues/skew-matrix form independent of the exporter's element formula.
    quaternion = np.asarray(q, dtype=np.float64)
    x, y, z, w = quaternion/np.linalg.norm(quaternion)
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    result = np.eye(4)
    result[:3, :3] = (np.eye(3)+2*w*cross+2*cross@cross)@np.diag(scale)
    result[:3, 3] = t
    return result


class AnimationMathGuards(unittest.TestCase):
    def test_equivalent_quaternion_signs_are_continuous(self):
        q = np.array([[[0, 0, 0, 1]], [[0, 0, 0, -1]], [[0, 0, 0, 1]]], dtype='f4')
        out, count = continuous_quaternions(q)
        self.assertEqual(count, 1)
        np.testing.assert_array_equal(out, np.tile([[[0, 0, 0, 1]]], (3, 1, 1)))
        np.testing.assert_array_equal(q[1], [[0, 0, 0, -1]])
        for invalid in (np.full((2, 1, 4), np.nan), np.zeros((2, 1, 4))):
            with self.assertRaises(ValueError): continuous_quaternions(invalid)

    def test_non_trs_matrices_rejected(self):
        for row, col, value in ((0, 1, .1), (0, 0, 0), (0, 0, -1), (3, 0, .1), (1, 1, np.inf)):
            m = np.eye(4)
            m[row, col] = value
            with self.assertRaises(ValueError): decompose_bind(m.T.flatten())


@unittest.skipUnless((OUT/'manifest.json').exists(), 'animated Elsa GLB not generated')
class RealElsaAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.base_binary = glb_read(ROOT/'analysis/elsa-model/elsa-yangcheng.colour-reference.glb')
        cls.doc, cls.binary = glb_read(OUT/'elsa-yangcheng.animated.glb')
        cls.report = json.loads((OUT/'export-report.json').read_text('utf8'))
        cls.library = parse_library((RECOVERED/'ailisha.gisacl').read_bytes())
        cls.names = [cls.base['nodes'][j]['name'] for j in cls.base['skins'][0]['joints']]
        cls.poses, cls.metadata = {}, {}
        for name in ('stand_idle', 'skin'):
            raw = (RECOVERED/(name+'.poses')).read_bytes()
            bones, frames, rate = struct.unpack_from('<IIf', raw, 8)
            cls.poses[name] = np.frombuffer(raw, dtype='<f4', offset=20).reshape(frames, bones, 10)
            cls.metadata[name] = json.loads((RECOVERED/(name+'.json')).read_text('utf8'))

    def test_manifest_identity_and_original_asset_bytes(self):
        manifest = json.loads((OUT/'manifest.json').read_text('utf8'))
        blob = (OUT/manifest['file']).read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), manifest['glbSha'])
        self.assertEqual(len(blob), manifest['bytes'])
        self.assertEqual(manifest['clipNames'], ['stand_idle', 'skin'])
        self.assertEqual(self.binary[:len(self.base_binary)], self.base_binary)
        for key in ('skins', 'meshes', 'materials', 'images', 'textures', 'samplers'):
            self.assertEqual(self.doc[key], self.base[key])
        self.assertEqual(len(self.doc['animations']), 2)
        self.assertFalse(self.doc['extras']['knownBindDifference']['correctionApplied'])

    def test_default_bind_nodes_use_trs_without_matrices(self):
        error = 0
        for node_id in self.doc['skins'][0]['joints']:
            node = self.doc['nodes'][node_id]
            self.assertNotIn('matrix', node)
            actual = trs_matrix(node['translation'], node['rotation'], node['scale'])
            source = np.array(self.base['nodes'][node_id]['matrix']).reshape(4, 4).T
            error = max(error, np.max(np.abs(actual-source)))
            self.assertAlmostEqual(np.linalg.norm(node['rotation']), 1, places=12)
        self.assertLess(error, 2e-7)

    def test_imported_hierarchy_paths_resolve_after_safe_mesh_rename(self):
        nodes = self.doc['nodes']
        mesh = nodes[0]
        self.assertEqual(mesh['name'], 'ElsaMesh')
        self.assertEqual(mesh['extras']['sourceNodeName'], self.base['nodes'][0]['name'])
        self.assertEqual(self.report['node_name_changes'], [{'node': 0,
            'source_name': self.base['nodes'][0]['name'], 'name': 'ElsaMesh'}])
        roots = self.doc['scenes'][self.doc.get('scene', 0)]['nodes']
        def walk(index, ancestors):
            node = nodes[index]
            self.assertNotIn('/', node['name'])
            self.assertNotIn('\\', node['name'])
            path = ancestors+[node['name']]
            children = roots
            target = None
            # Cocos Node.getChildByPath splits '/' and looks up each direct child.
            for segment in '/'.join(path).split('/'):
                found = [i for i in children if nodes[i]['name'] == segment]
                self.assertEqual(len(found), 1)
                target = found[0]
                children = nodes[target].get('children', [])
            self.assertEqual(target, index)
            for child in node.get('children', []):
                walk(child, path)
        for root in roots:
            walk(root, [])

    def test_every_track_key_matches_real_pose_and_original_rate(self):
        joints = self.doc['skins'][0]['joints']
        for anim in self.doc['animations']:
            name = anim['name']
            p, meta = self.poses[name], self.metadata[name]
            node_tracks = {joints[r['mesh_joint']]: r['clip_index'] for r in meta['bone_mapping']}
            targets = set()
            self.assertEqual(len(anim['channels']), 540)
            for channel in anim['channels']:
                node, path = channel['target']['node'], channel['target']['path']
                self.assertNotIn((node, path), targets)
                targets.add((node, path))
                self.assertEqual(self.doc['nodes'][node]['name'], meta['bone_mapping'][node_tracks[node]]['name'])
                sampler = anim['samplers'][channel['sampler']]
                self.assertEqual(sampler['interpolation'], 'LINEAR')
                times = read_accessor(self.doc, self.binary, sampler['input'])[:, 0]
                expected_times = (np.arange(len(p))/meta['sample_rate']).astype('f4')
                np.testing.assert_array_equal(times, expected_times)
                self.assertTrue(np.all(np.diff(times) > 0))
                accessor = self.doc['accessors'][sampler['input']]
                self.assertEqual(accessor['min'], [float(times[0])])
                self.assertEqual(accessor['max'], [float(times[-1])])
                actual = read_accessor(self.doc, self.binary, sampler['output'])
                sl = {'rotation': slice(0, 4), 'translation': slice(4, 7), 'scale': slice(7, 10)}[path]
                expected = p[:, node_tracks[node], sl]
                if path == 'rotation':
                    self.assertTrue(np.all(np.all(actual == expected, axis=1) | np.all(actual == -expected, axis=1)))
                    self.assertTrue(np.all(np.sum(actual[:-1]*actual[1:], axis=1) >= 0))
                    self.assertLess(np.max(np.abs(np.sum(actual**2, axis=1)-1)), 3e-7)
                else:
                    np.testing.assert_array_equal(actual, expected)
                self.assertTrue(np.all(np.isfinite(actual)))
            self.assertEqual(targets, {(node, prop) for node in joints for prop in ('rotation', 'translation', 'scale')})

    def test_pose_and_mapping_tampering_rejected(self):
        for altered_file in ('stand_idle.poses', 'stand_idle.json'):
            def fake_read(path, maximum=80_000_020):
                raw = read_bounded(path, maximum)
                if path.name != altered_file: return raw
                if path.suffix == '.poses':
                    raw = bytearray(raw)
                    struct.pack_into('<f', raw, 36, 1.25)  # finite translation, valid format, wrong hash
                    return bytes(raw)
                obj = json.loads(raw)
                obj['bone_mapping'][0]['mesh_joint'] = 1
                return json.dumps(obj).encode('utf8')
            with patch('export_elsa_animation.read_bounded', side_effect=fake_read):
                with self.assertRaisesRegex(ValueError, 'hash mismatch|mapping differs'):
                    load_clip(RECOVERED, 'stand_idle', self.library, self.names)

    def test_independent_source_cpu_skinning_at_selected_frames(self):
        d, b = self.base, self.base_binary
        skin = d['skins'][0]
        parents = {child: i for i, n in enumerate(d['nodes']) for child in n.get('children', [])}
        parts = d['meshes'][0]['primitives']
        positions = np.concatenate([read_accessor(d, b, p['attributes']['POSITION']) for p in parts])
        influences = np.concatenate([read_accessor(d, b, p['attributes']['JOINTS_0']) for p in parts]).astype(int)
        weights = np.concatenate([read_accessor(d, b, p['attributes']['WEIGHTS_0']) for p in parts])
        ibm = read_accessor(d, b, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
        homogeneous = np.column_stack((positions, np.ones(len(positions))))
        for name in ('stand_idle', 'skin'):
            meta = self.metadata[name]
            mapping = {skin['joints'][r['mesh_joint']]: r['clip_index'] for r in meta['bone_mapping']}
            verification = next(r for r in self.report['verification'] if r['name'] == name)
            first = None
            for row in verification['selected_frame_bounds']:
                source = self.poses[name][row['frame']]
                worlds = {}
                def world(i):
                    if i not in worlds:
                        if i in mapping:
                            pose = source[mapping[i]]
                            local = trs_matrix(pose[4:7], pose[:4], pose[7:])
                        else: local = np.eye(4)
                        worlds[i] = world(parents[i])@local if i in parents else local
                    return worlds[i]
                transforms = np.array([world(i) for i in skin['joints']])@ibm
                posed = np.zeros((len(positions), 4))
                for influence in range(4):
                    matrices = transforms[influences[:, influence]]
                    transformed = np.matmul(matrices, homogeneous[:, :, None])[:, :, 0]
                    posed += transformed*weights[:, influence, None]
                result = posed[:, :3]
                if first is None: first = result
                np.testing.assert_allclose(result.min(axis=0), row['min'], atol=1e-5, rtol=0)
                np.testing.assert_allclose(result.max(axis=0), row['max'], atol=1e-5, rtol=0)
                movement = np.linalg.norm(result-first, axis=1)
                self.assertAlmostEqual(float(movement.max()), row['max_displacement_from_first_frame'], places=5)
                self.assertEqual(int(np.sum(movement > 1e-4)), row['vertices_moving_over_1e_4'])

    def test_real_motion_and_constant_skin_remain_distinct(self):
        moving = self.poses['stand_idle']
        constant = self.poses['skin']
        self.assertEqual(int(np.sum(np.any(np.ptp(moving, axis=0) > 1e-6, axis=1))), 136)
        self.assertEqual(float(np.ptp(constant, axis=0).max()), 0)
        reports = {r['name']: r for r in self.report['verification']}
        self.assertGreater(reports['stand_idle']['max_vertex_displacement_from_first_frame'], .6)
        self.assertEqual(reports['skin']['max_vertex_displacement_from_first_frame'], 0)
        # Toe source rotation is retained, not replaced by the mesh bind rotation.
        toe = 50
        q = constant[0, toe, :4]
        node = self.doc['nodes'][self.doc['skins'][0]['joints'][toe]]
        self.assertLess(abs(float(np.dot(q, node['rotation']))), .9999)


if __name__ == '__main__':
    unittest.main()
