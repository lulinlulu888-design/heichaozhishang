"""Real pinned enemy clip decoding and rejection boundaries; no game execution."""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import sample_tutorial_enemy_animation as enemy
from inspect_neox_animation import map_bones

POSE_SHA = {
    'idle': 'f3701f3ab70cf0998a185463af3d2c8f27f2445d40f18bb2453575c628b90d22',
    'fire': '4807abe1058d438b2873bb73bd266fe397a142a7063b8e57f6cc6cdca22bdcf6',
}


class TutorialEnemyAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Required local evidence must exist; missing inputs fail, not skip.
        cls.resources, _, cls.library, cls.model = enemy.inputs()
        cls.decoder = enemy.decoder_provenance()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hczs-enemy-acl-test-')
        self.path = Path(self.temporary.name).resolve()
        self.assertIn(Path(tempfile.gettempdir()).resolve(), self.path.parents)
        self.addCleanup(self.temporary.cleanup)

    def run_decoder(self, source, destination):
        return subprocess.run([str(enemy.SAMPLER), str(source), str(destination)],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def check_clip(self, name):
        raw = (enemy.OUT/(name+'.gisacl')).read_bytes()
        parsed, acl = enemy.validate_clip(name, raw, self.library, self.model)
        self.assertEqual(hashlib.sha256(acl).hexdigest(), enemy.CLIPS[name]['acl_sha256'])
        output = self.path/(name+'.poses')
        source = self.path/(name+'.acl')
        source.write_bytes(acl)
        first = self.run_decoder(source, output)
        self.assertEqual(first.returncode, 0, first.stderr)
        receipt = json.loads(first.stdout)
        self.assertEqual(receipt['inputSha256'], enemy.CLIPS[name]['acl_sha256'])
        self.assertEqual(receipt['clipName'], f'tutorial_enemy_{name}.acl')
        self.assertEqual(receipt['aclVersion'], '1.2.0')
        self.assertEqual(receipt['binaryVersion'], 4)
        self.assertTrue(receipt['hashVerified'])
        self.assertEqual(receipt['validationScope'], 'sha256-pinned-original-clips-only')
        data = output.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), POSE_SHA[name])
        self.assertEqual(data, (enemy.OUT/(name+'.poses')).read_bytes())
        signature, bones, frames, rate = struct.unpack_from('<8sIIf', data)
        self.assertEqual(signature, b'HCZPOSE1')
        self.assertEqual((bones, frames, rate), (61, enemy.CLIPS[name]['samples'], 30.0))
        self.assertEqual(len(data), 20+40*bones*frames)
        for pose in struct.iter_unpack('<10f', memoryview(data)[20:]):
            self.assertTrue(all(math.isfinite(value) for value in pose))
            self.assertLess(abs(sum(value*value for value in pose[:4])-1), 2e-7)
        output.write_bytes(b'prior artifact')
        second = self.run_decoder(source, output)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(output.read_bytes(), data)
        self.assertEqual(json.loads(second.stdout), receipt)
        self.assertEqual(source.read_bytes(), acl)
        self.assertEqual(list(self.path.glob('.acl-sample-*.tmp')), [])
        self.assertEqual(len(parsed['bone_mapping']), 61)

    def test_idle_real_decoder_samples_and_determinism(self):
        self.check_clip('idle')

    def test_fire_real_decoder_samples_and_determinism(self):
        self.check_clip('fire')

    def test_decoder_preserves_elsa_pins_and_adds_only_two_enemy_pins(self):
        self.assertEqual(set(self.decoder['acceptedInputSha256']), {
            'stand_idle.acl', 'skin.acl', 'tutorial_enemy_idle.acl', 'tutorial_enemy_fire.acl'})
        self.assertEqual(self.decoder['wrapperSha256'], enemy.WRAPPER_SHA)
        self.assertEqual(hashlib.sha256(enemy.SAMPLER.read_bytes()).hexdigest(), self.decoder['executableSha256'])

    def test_all_tracks_match_names_and_reordering_is_not_assumed(self):
        for name in enemy.CLIPS:
            metadata = json.loads((enemy.OUT/(name+'.json')).read_text('utf8'))
            _, acl = enemy.validate_clip(name, (enemy.OUT/(name+'.gisacl')).read_bytes(), self.library, self.model)
            self.assertEqual(metadata['source']['index'], enemy.CLIPS[name]['npk_index'])
            self.assertEqual(metadata['library_record']['index'], enemy.CLIPS[name]['library_index'])
            self.assertEqual({row['mesh_joint'] for row in metadata['bone_mapping']}, set(range(61)))
            self.assertEqual({row['library_index'] for row in metadata['bone_mapping']}, set(range(61)))
            # Changing only the target list order must change the numeric mapping,
            # retaining ID/name identity instead of silently using track ordinal.
            reversed_names = [bone['name'] for bone in reversed(self.model['bones'])]
            remapped = map_bones(self.library, metadata, reversed_names)
            for original, shuffled in zip(metadata['bone_mapping'], remapped):
                self.assertEqual(original['name'], shuffled['name'])
                self.assertEqual(original['bone_id'], shuffled['bone_id'])
                self.assertEqual(shuffled['mesh_joint'], 60-original['mesh_joint'])

    def test_unknown_or_duplicate_skeleton_name_rejected(self):
        metadata = json.loads((enemy.OUT/'idle.json').read_text('utf8'))
        names = [bone['name'] for bone in self.model['bones']]
        with self.assertRaisesRegex(ValueError, 'identities differ'):
            map_bones(self.library, metadata, ['not-the-source-bone']+names[1:])
        with self.assertRaisesRegex(ValueError, 'duplicate model'):
            map_bones(self.library, metadata, [names[1]]+names[1:])

    def test_clip_wrapper_tampering_rejected_before_sampler(self):
        raw = bytearray((enemy.OUT/'idle.gisacl').read_bytes())
        raw[4] ^= 1
        with self.assertRaisesRegex(ValueError, 'wrapper SHA-256'):
            enemy.validate_clip('idle', raw, self.library, self.model)
        with self.assertRaisesRegex(ValueError, 'only tutorial'):
            enemy.validate_clip('unknown', raw, self.library, self.model)

    def test_rehashed_unknown_acl_is_rejected_and_preserves_output(self):
        for name in enemy.CLIPS:
            raw = bytearray((enemy.OUT/(name+'.acl')).read_bytes())
            raw[-1] ^= 1
            # Make its legacy FNV match again: only cryptographic pinning should
            # decide whether these unfamiliar bytes may reach the old decoder.
            struct.pack_into('<I', raw, 4, enemy.fnv32(raw[8:]))
            self.assertEqual(struct.unpack_from('<I', raw, 4)[0], enemy.fnv32(raw[8:]))
            source, target = self.path/(name+'.bad.acl'), self.path/(name+'.poses')
            source.write_bytes(raw); target.write_bytes(b'unchanged artifact')
            result = self.run_decoder(source, target)
            self.assertEqual(result.returncode, 1)
            self.assertIn('unsupported ACL SHA-256', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(target.read_bytes(), b'unchanged artifact')
            self.assertEqual(list(self.path.glob('.acl-sample-*.tmp')), [])

    def test_source_samples_have_real_motion_and_exact_sample_anchors(self):
        idle = (enemy.OUT/'idle.poses').read_bytes()
        fire = (enemy.OUT/'fire.poses').read_bytes()
        def pose(data, frame, track):
            return struct.unpack_from('<10f', data, 20+(frame*61+track)*40)
        # Independent byte-offset reads of previously inspected original samples.
        self.assertEqual(pose(idle, 0, 60)[4:7], (0.005366206634789705, 12.751466751098633, -1.0059787034988403))
        self.assertEqual(pose(idle, 50, 60)[5], 13.966865539550781)
        self.assertEqual(pose(fire, 17, 59)[4:7], (12.542064666748047, 9.61611270904541, -2.9542524814605713))
        self.assertGreater(abs(pose(fire, 17, 59)[4]-pose(fire, 0, 59)[4]), 11)
        self.assertEqual(pose(idle, 100, 60)[4:7], pose(idle, 0, 60)[4:7])
        # Some other source tracks differ at the endpoints; no loop repair.
        self.assertNotEqual(idle[20:20+61*40], idle[-61*40:])
        for name, expected_indices in [('idle', [0, 50, 100]), ('fire', [0, 17, 35])]:
            report = json.loads((enemy.OUT/(name+'.motion.json')).read_text('utf8'))
            self.assertEqual([row['frame'] for row in report['frame_samples']], expected_indices)
            self.assertEqual([row['source_time_seconds'] for row in report['frame_samples']], [frame/30 for frame in expected_indices])
            self.assertFalse(report['loop_correction_applied'])

    def test_reference_pose_and_global_mesh_hierarchy_agree_without_correction(self):
        report = enemy.reference_bind_comparison(self.library, self.model)
        self.assertEqual(len(report['rows']), 61)
        self.assertLess(report['max_local_matrix_component_error'], 1e-6)
        self.assertGreater(max(row['max_reference_vs_raw'] for row in report['rows']), 9)
        self.assertFalse(report['raw_matrices_or_samples_modified'])

    def test_nonfinite_and_truncated_pose_artifacts_rejected(self):
        original = (enemy.OUT/'idle.poses').read_bytes()
        damaged = bytearray(original); struct.pack_into('<f', damaged, 20+16, float('nan'))
        mapping = json.loads((enemy.OUT/'idle.json').read_text('utf8'))['bone_mapping']
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            enemy.motion_summary(damaged, mapping)
        with self.assertRaisesRegex(ValueError, 'length'):
            enemy.motion_summary(original[:-1], mapping)

    def test_output_directory_cannot_escape_owned_analysis_tree(self):
        with self.assertRaisesRegex(ValueError, 'output must remain'):
            enemy.recover(Path('does-not-exist.apk'), self.path)


if __name__ == '__main__':
    unittest.main()
