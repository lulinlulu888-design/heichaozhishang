"""Independent output reads and failure checks for the original enemy animations."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'tests'))
import export_tutorial_enemy_animation as exporter
from test_elsa_animation import glb_read, read_accessor, trs_matrix

BASE = ROOT/'analysis/tutorial-enemy/tutorial-enemy-991.colour-reference.glb'
RECOVERED = ROOT/'analysis/tutorial-enemy-animation'
OUT = ROOT/'analysis/tutorial-enemy-animated'


@unittest.skipUnless((OUT/'manifest.json').exists(), 'enemy animation GLB not generated')
class OriginalEnemyAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.base_binary = glb_read(BASE)
        cls.doc, cls.binary = glb_read(OUT/'tutorial-enemy-991.animated.glb')
        cls.report = json.loads((OUT/'export-report.json').read_text('utf8'))
        cls.metadata, cls.poses = {}, {}
        for name in ('idle', 'fire'):
            cls.metadata[name] = json.loads((RECOVERED/(name+'.json')).read_text('utf8'))
            raw = (RECOVERED/(name+'.poses')).read_bytes()
            bones, frames, rate = struct.unpack_from('<IIf', raw, 8)
            assert bones == 61 and rate == 30 and frames == {'idle': 101, 'fire': 36}[name]
            cls.poses[name] = np.frombuffer(raw, dtype='<f4', offset=20).reshape(frames, bones, 10)

    def test_source_asset_bytes_and_confidence_are_preserved(self):
        manifest = json.loads((OUT/'manifest.json').read_text('utf8'))
        raw = (OUT/manifest['file']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['glbSha'])
        self.assertEqual(len(raw), manifest['bytes'])
        self.assertEqual(manifest['clipNames'], ['idle', 'fire'])
        self.assertEqual(self.binary[:len(self.base_binary)], self.base_binary)
        for key in ('skins', 'meshes', 'materials', 'textures', 'images', 'samplers'):
            self.assertEqual(self.base[key], self.doc[key])
        for key, value in self.base['extras'].items():
            if key != 'missing':
                self.assertEqual(self.doc['extras'][key], value)
        self.assertEqual(len(self.doc['extras']['missing']), len(self.base['extras']['missing']))
        self.assertFalse(any('Animation clips,' in item for item in self.doc['extras']['missing']))
        for item in self.base['extras']['missing']:
            if not item.startswith('Animation clips,'):
                self.assertIn(item, self.doc['extras']['missing'])
        self.assertNotIn('knownBindDifference', self.doc['extras'])
        self.assertFalse(any(n.get('name', '').startswith('Elsa') for n in self.doc['nodes']))
        self.assertFalse(self.doc['extras']['animationRecovery']['enginePlaybackVerified'])
        self.assertEqual([n['name'] for n in self.base['nodes']], [n['name'] for n in self.doc['nodes']])

    def test_default_local_bind_trs_preserves_original_matrices(self):
        joints = self.doc['skins'][0]['joints']
        self.assertEqual(len(joints), 61)
        for i in joints:
            node = self.doc['nodes'][i]
            self.assertNotIn('matrix', node)
            matrix = trs_matrix(node['translation'], node['rotation'], node['scale'])
            source = np.array(self.base['nodes'][i]['matrix']).reshape(4, 4).T
            np.testing.assert_allclose(matrix, source, atol=4e-7, rtol=0)

    def test_all_8357_bone_frames_match_named_source_tracks(self):
        joints = self.doc['skins'][0]['joints']
        verified = 0
        self.assertEqual([a['name'] for a in self.doc['animations']], ['idle', 'fire'])
        for animation in self.doc['animations']:
            name = animation['name']
            meta, poses = self.metadata[name], self.poses[name]
            mapping = {joints[row['mesh_joint']]: row for row in meta['bone_mapping']}
            seen = set()
            for channel in animation['channels']:
                node, path = channel['target']['node'], channel['target']['path']
                self.assertNotIn((node, path), seen)
                seen.add((node, path))
                row = mapping[node]
                self.assertEqual(self.doc['nodes'][node]['name'], row['name'])
                sampler = animation['samplers'][channel['sampler']]
                self.assertEqual(sampler['interpolation'], 'LINEAR')
                times = read_accessor(self.doc, self.binary, sampler['input'])[:, 0]
                np.testing.assert_array_equal(times, (np.arange(len(poses))/30).astype('f4'))
                actual = read_accessor(self.doc, self.binary, sampler['output'])
                sl = {'rotation': slice(0, 4), 'translation': slice(4, 7), 'scale': slice(7, 10)}[path]
                expected = poses[:, row['clip_index'], sl]
                if path == 'rotation':
                    self.assertTrue(np.all(np.all(actual == expected, axis=1) | np.all(actual == -expected, axis=1)))
                    self.assertTrue(np.all(np.sum(actual[:-1]*actual[1:], axis=1) >= 0))
                else:
                    np.testing.assert_array_equal(actual, expected)
            self.assertEqual(seen, {(j, p) for j in joints for p in ('translation', 'rotation', 'scale')})
            verified += len(poses)*61
        self.assertEqual(verified, 8357)

    def test_independent_cpu_skinning_and_retained_loop_difference(self):
        doc, binary = self.base, self.base_binary
        skin = doc['skins'][0]
        attrs = doc['meshes'][0]['primitives'][0]['attributes']
        positions = read_accessor(doc, binary, attrs['POSITION'])
        influences = read_accessor(doc, binary, attrs['JOINTS_0']).astype(int)
        weights = read_accessor(doc, binary, attrs['WEIGHTS_0'])
        homogeneous = np.column_stack((positions, np.ones(len(positions))))
        ibms = read_accessor(doc, binary, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
        parents = {child: i for i, node in enumerate(doc['nodes']) for child in node.get('children', [])}
        for report in self.report['verification']:
            name = report['name']
            mapping = {skin['joints'][r['mesh_joint']]: r['clip_index'] for r in self.metadata[name]['bone_mapping']}
            first = None
            for frame in report['selected_frame_bounds']:
                source = self.poses[name][frame['frame']]
                worlds = {}
                def world(i):
                    if i not in worlds:
                        if i in mapping:
                            pose = source[mapping[i]]
                            local = trs_matrix(pose[4:7], pose[:4], pose[7:])
                        else:
                            local = np.eye(4)
                        worlds[i] = world(parents[i])@local if i in parents else local
                    return worlds[i]
                transforms = np.array([world(i) for i in skin['joints']])@ibms
                result = np.zeros((len(positions), 4))
                for influence in range(4):
                    transformed = np.matmul(transforms[influences[:, influence]], homogeneous[:, :, None])[:, :, 0]
                    result += transformed*weights[:, influence, None]
                result = result[:, :3]
                if first is None:
                    first = result.copy()
                np.testing.assert_allclose(result.min(axis=0), frame['min'], atol=1e-6, rtol=0)
                np.testing.assert_allclose(result.max(axis=0), frame['max'], atol=1e-6, rtol=0)
                self.assertAlmostEqual(float(np.linalg.norm(result-first, axis=1).max()), frame['max_displacement_from_first_frame'], places=6)
            self.assertGreater(report['selected_frame_bounds'][-1]['max_displacement_from_first_frame'], .001)

    def test_unpinned_input_rejected_before_replacing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            destination = out/'tutorial-enemy-991.animated.glb'
            destination.write_bytes(b'previous verified output')
            altered = out/'changed.glb'
            raw = bytearray(BASE.read_bytes())
            raw[-20] ^= 1
            altered.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                exporter.run(altered, RECOVERED, out)
            self.assertEqual(destination.read_bytes(), b'previous verified output')
            self.assertFalse((out/'tutorial-enemy-991.animated.glb.pending').exists())

    def test_consistent_but_unpinned_pose_metadata_cannot_be_substituted(self):
        original_loader = exporter.load_clip
        def substituted(*args):
            clip = copy.deepcopy(original_loader(*args))
            clip['pose_sha256'] = '0'*64
            clip['metadata']['poses']['sha256'] = '0'*64
            return clip
        with patch.object(exporter, 'load_clip', side_effect=substituted):
            with self.assertRaisesRegex(ValueError, 'pinned clip identity mismatch'):
                exporter.load_inputs(BASE, RECOVERED)


if __name__ == '__main__':
    unittest.main()
