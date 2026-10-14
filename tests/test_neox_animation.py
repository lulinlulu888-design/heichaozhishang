"""Actual-file identity checks and rejected boundary cases for animation data."""
from pathlib import Path
import copy
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from inspect_neox_animation import (bone_id, clip_path, cstring, map_bones,
                                     parse_clip, parse_library, sample_clip, summarize_poses)
from inspect_neox_model import parse_model
from neox_resource_paths import lookup_logical

DATA = ROOT/'analysis/animation/recovered'


class AnimationEvidence(unittest.TestCase):
    def test_empty_root_opt_in_preserves_other_name_validation(self):
        raw=bytearray(self.raw_library)
        offset=self.library['clips'][0]['offset']
        raw[offset+32:offset+64]=bytes(32)
        with self.assertRaisesRegex(ValueError,'empty name'):
            parse_library(bytes(raw))
        accepted=parse_library(bytes(raw),allow_empty_roots=True)
        self.assertEqual(accepted['clips'][0]['root_bone'],'')
        self.assertEqual(accepted['bone_names'],self.library['bone_names'])
        self.assertEqual(accepted['coverage_bytes'],len(raw))
        raw[offset:offset+32]=bytes(32)
        with self.assertRaisesRegex(ValueError,'empty name'):
            parse_library(bytes(raw),allow_empty_roots=True)
        raw=bytearray(self.raw_library); raw[14:46]=bytes(32)
        with self.assertRaisesRegex(ValueError,'empty name'):
            parse_library(bytes(raw),allow_empty_roots=True)

    @classmethod
    def setUpClass(cls):
        cls.raw_library = (DATA/'ailisha.gisacl').read_bytes()
        cls.library = parse_library(cls.raw_library)
        cls.raw_clip = (DATA/'stand_idle.gisacl').read_bytes()
        cls.clip = parse_clip(cls.raw_clip)
        cls.model = parse_model((ROOT/'analysis/resource-mapping/elsa-yangcheng.mesh').read_bytes())

    def test_complete_library_and_unique_clip_paths(self):
        lib = self.library
        self.assertEqual((lib['bone_count'], lib['clip_count'], lib['coverage_bytes']), (180, 75, 96082))
        catalogue = json.loads((ROOT/'analysis/resource-mapping/npk-indices.json').read_text('utf8'))
        paths = [clip_path('character/player/ailisha/ailisha.gisacl', clip['name']) for clip in lib['clips']]
        self.assertEqual(len(set(paths)), 75)
        for path in paths:
            self.assertEqual(len(lookup_logical(catalogue, path)), 1)
        self.assertEqual(paths[0], 'character/player/ailisha/ailisha_gis_acl/skin.gisacl')

    def test_fixed_bone_ids_and_all_180_mapping(self):
        self.assertEqual(bone_id('bip001'), 0xbb026d21)
        self.assertEqual(bone_id('bip001 head'), 0x3e41733a)
        self.assertEqual(bone_id('bip001 l calf'), 0xd1b23809)
        names = [b['name'] for b in self.model['bones']]
        mapping = map_bones(self.library, self.clip, names)
        self.assertEqual(len(mapping), 180)
        self.assertTrue(all(row['clip_index'] == row['library_index'] == row['mesh_joint'] for row in mapping))
        # Mapping is by identity, never silently by order.
        reordered = map_bones(self.library, self.clip, list(reversed(names)))
        self.assertTrue(all(row['clip_index'] == 179-row['mesh_joint'] for row in reordered))

    def test_authored_duration_matches_independent_acl_header(self):
        record = next(c for c in self.library['clips'] if c['name'] == 'stand_idle')
        self.assertAlmostEqual(record['duration_ms'], self.clip['duration_seconds'] * 1000, delta=0.001)
        for value in (-1.0, float('inf'), float('nan')):
            with self.subTest(value=value):
                bad = bytearray(self.raw_library)
                struct.pack_into('<f', bad, record['duration_field_offset'], value)
                with self.assertRaisesRegex(ValueError, 'invalid clip duration'):
                    parse_library(bad)

    def test_bone_mismatch_and_duplicate_rejected(self):
        names = [b['name'] for b in self.model['bones']]
        with self.assertRaises(ValueError):
            map_bones(self.library, self.clip, names[:-1]+['wrong'])
        with self.assertRaises(ValueError):
            map_bones(self.library, self.clip, names[:-1]+[names[0]])
        bad = copy.deepcopy(self.clip)
        bad['bone_ids'][0] ^= 1
        with self.assertRaises(ValueError):
            map_bones(self.library, bad, names)

    def test_two_observed_clip_headers(self):
        self.assertEqual((self.clip['acl_offset'], self.clip['acl_bytes'], self.clip['samples'],
                          self.clip['sample_rate'], self.clip['duration_seconds']), (740, 52519, 121, 30.0, 4.0))
        skin = parse_clip((DATA/'skin.gisacl').read_bytes())
        self.assertEqual((skin['acl_bytes'], skin['samples'], skin['sample_rate']), (4851, 318, 45.0))
        self.assertEqual(skin['bone_ids'], self.clip['bone_ids'])
        self.assertFalse(skin['acl_hash_verified']) # Header parsing is not full ACL verification.

    def test_names_ignore_padding_but_reject_bad_path(self):
        self.assertEqual(cstring(b'buff_1\0dle'+bytes(22)), 'buff_1')
        for value in (bytes(32), b'a'*32):
            with self.assertRaises(ValueError):
                cstring(value)
        for name in ('../escape', '', 'a/b', 'a\\b', 'x\0y'):
            with self.assertRaises(ValueError):
                clip_path('character/test.gisacl', name)
        for name in ('', 'x\0y'):
            with self.assertRaises(ValueError):
                bone_id(name)

    def test_library_length_version_count_and_record_guards(self):
        raw = self.raw_library
        for malformed in (b'', raw[:14], raw[:-1], raw+b'\0', b'FAIL'+raw[4:],
                          raw[:4]+struct.pack('<I', 0x03060000)+raw[8:],
                          raw[:8]+struct.pack('<H', 0xffff)+raw[10:],
                          raw[:10]+struct.pack('<I', 0xffffffff)+raw[14:],
                          raw[:12978]+struct.pack('<I', 1107)+raw[12982:]):
            with self.assertRaises(ValueError):
                parse_library(malformed)

    def test_library_nonfinite_and_nonunit_pose_rejected(self):
        for offset, value in ((5774, float('nan')), (5786, 9.0)):
            data = bytearray(self.raw_library)
            struct.pack_into('<f', data, offset, value)
            with self.assertRaises(ValueError):
                parse_library(bytes(data))

    def test_clip_wrapper_consistency_and_length(self):
        raw = self.raw_clip
        variants = [b'', raw[:4], raw[:-1], raw+b'\0']
        for offset, value in ((0, 0xffffffff), (8, self.clip['bone_ids'][0]), (732, 0xffffffff),
                              (736, 0), (740, 4), (748, 0), (768, 0xffffffff)):
            bad = bytearray(raw)
            struct.pack_into('<I', bad, offset, value)
            variants.append(bytes(bad))
        for malformed in variants:
            with self.assertRaises(ValueError):
                parse_clip(malformed)

    def test_pose_summary_and_boundary_rejections(self):
        header = b'HCZPOSE1'+struct.pack('<IIf', 1, 2, 30.0)
        a = (0, 0, 0, 1, 1, 2, 3, 1, 1, 1)
        b = (0, 0, 0, 1, 1, 4, 3, 1, 1, 1)
        data = header + struct.pack('<20f', *(a+b))
        summary = summarize_poses(data)
        self.assertEqual(summary['max_translation_component_change_from_first_frame'], 2.0)
        self.assertEqual(summary['frames'], 2)
        bad_float = bytearray(data)
        struct.pack_into('<f', bad_float, 20, float('nan'))
        bad_quat = bytearray(data)
        struct.pack_into('<f', bad_quat, 20, 3.0)
        for malformed in (b'', data[:20], data[:-1], data+b'\0', bytes(bad_float), bytes(bad_quat),
                          data[:8]+struct.pack('<I', 0xffffffff)+data[12:]):
            with self.assertRaises(ValueError):
                summarize_poses(malformed)

    def test_unambiguous_source_sidecars(self):
        for filename, index in (('ailisha.gisacl', 134), ('stand_idle.gisacl', 4504), ('skin.gisacl', 4964)):
            source = json.loads((DATA/(filename+'.source.json')).read_text('utf8'))
            self.assertEqual(source['index'], index)
            self.assertEqual(source['decoded_size'], (DATA/filename).stat().st_size)
            self.assertTrue(source['logical_path'].endswith(filename))

    def test_sampler_success_without_new_output_cannot_reuse_stale_pose(self):
        stdout = json.dumps({'aclVersion': '1.2.0', 'binaryVersion': 4, 'hashVerified': True,
                             'bones': 180, 'samples': 121, 'sampleRate': 30,
                             'inputSha256': self.clip['acl_sha256']})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'existing.poses'
            path.write_bytes(b'previous-good-output')
            with patch('inspect_neox_animation.subprocess.run',
                       return_value=subprocess.CompletedProcess([], 0, stdout=stdout)):
                with self.assertRaisesRegex(ValueError, 'invalid sampled pose file'):
                    sample_clip(Path('fake-sampler'), DATA/'stand_idle.acl', path, self.clip)
            self.assertEqual(path.read_bytes(), b'previous-good-output')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_sampler_false_or_mismatched_report_rejected(self):
        good = {'aclVersion': '1.2.0', 'binaryVersion': 4, 'hashVerified': True,
                'bones': 180, 'samples': 121, 'sampleRate': 30,
                'inputSha256': self.clip['acl_sha256']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'existing.poses'
            path.write_bytes(b'previous-good-output')
            for field, value in (('hashVerified', 1), ('binaryVersion', 5), ('bones', 179),
                                  ('samples', 122), ('sampleRate', 45), ('inputSha256', 'wrong')):
                with patch('inspect_neox_animation.subprocess.run',
                           return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(good | {field: value}))):
                    with self.assertRaisesRegex(ValueError, 'sampler report does not match'):
                        sample_clip(Path('fake-sampler'), DATA/'stand_idle.acl', path, self.clip)
                self.assertEqual(path.read_bytes(), b'previous-good-output')
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
