"""Synthetic checks for the hero idle export gates (no APK needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_neox_animation import bone_id, map_bones
from verify_lynn_idle import SAMPLED_SKIN_ENVELOPE, SAMPLED_STRETCH_ENVELOPE, inside


def library(*names):
    return dict(bone_names=list(names))


def clip(*names):
    return dict(bone_ids=[bone_id(name) for name in names])


class MapBonesTest(unittest.TestCase):
    def test_exact_skeleton_maps_every_mesh_joint(self):
        rows = map_bones(library('root', 'arm'), clip('arm', 'root'), ['root', 'arm'])
        self.assertEqual([(r['name'], r['mesh_joint'], r['clip_index']) for r in rows], [('arm', 1, 0), ('root', 0, 1)])

    def test_tracks_outside_the_library_are_ignored_with_extras(self):
        rows = map_bones(library('root', 'arm'), clip('root', 'arm', 'prop'), ['root', 'arm'], allow_library_extras=True)
        self.assertEqual([r['name'] for r in rows], ['root', 'arm'])

    def test_untracked_library_bone_is_allowed_only_off_mesh(self):
        rows = map_bones(library('root', 'arm', 'ribbon'), clip('root', 'arm'), ['root', 'arm'], allow_library_extras=True)
        self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, 'untrackedMeshBones.*ribbon'):
            map_bones(library('root', 'arm', 'ribbon'), clip('root', 'arm'), ['root', 'arm', 'ribbon'], allow_library_extras=True)

    def test_strict_mode_still_requires_identical_tracks(self):
        with self.assertRaises(ValueError):
            map_bones(library('root', 'arm'), clip('root', 'arm', 'prop'), ['root', 'arm'])


class EnvelopeTest(unittest.TestCase):
    def test_strong_pose_with_rigid_triangles_passes_stretch_only(self):
        stats = dict(diagonal_ratio=0.95, median_displacement_over_height=0.16, p95_displacement_over_height=0.53,
                     edge_log_stretch_p99=0.33, edge_log_stretch_p999=0.82)
        self.assertFalse(inside(stats, SAMPLED_SKIN_ENVELOPE))
        self.assertTrue(inside(stats, SAMPLED_STRETCH_ENVELOPE))

    def test_exploded_skin_fails_both(self):
        stats = dict(diagonal_ratio=0.66, median_displacement_over_height=0.14, p95_displacement_over_height=0.46,
                     edge_log_stretch_p99=6.06, edge_log_stretch_p999=9.0)
        self.assertFalse(inside(stats, SAMPLED_SKIN_ENVELOPE))
        self.assertFalse(inside(stats, SAMPLED_STRETCH_ENVELOPE))


if __name__ == '__main__':
    unittest.main()
