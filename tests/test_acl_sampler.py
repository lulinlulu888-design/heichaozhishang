"""Exercise the pinned native ACL data decoder, never the game executable.

Requires tools/setup_acl_sampler.py and the two recovered original clips.
Unknown content must be rejected before ACL decoding even with a valid FNV32.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SAMPLER = ROOT / "tools/runtime/acl-1.2.0/build/Release/acl-sample.exe"
CLIPS = {
    "stand_idle": "cda4d69e000276ee263a47d5531c43cbc6ae84ff6e133d64fbeeb7ccb7de898f",
    "skin": "6bf93b1e7791dd6124a6e13c26538cfeac56d65c0d49abffc68a818c06be4cbd",
}


def fnv32(data):
    result = 2166136261
    for value in data:
        result = ((result ^ value) * 16777619) & 0xffffffff
    return result


def with_valid_fnv(data):
    result = bytearray(data)
    struct.pack_into("<I", result, 4, fnv32(result[8:]))
    return result


@unittest.skipUnless(SAMPLER.is_file(), "requires tools/setup_acl_sampler.py")
@unittest.skipUnless(all((ROOT / f"analysis/animation/{name}.acl").is_file()
                        for name in CLIPS), "requires recovered original ACL clips")
class AclSampler(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="hczs-acl-test-")
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name)

    def run_sampler(self, source, target):
        return subprocess.run([str(SAMPLER), str(source), str(target)],
                              capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def source(self, name="stand_idle"):
        return ROOT / f"analysis/animation/{name}.acl"

    def assert_no_temporary_output(self):
        self.assertEqual(list(self.folder.glob(".acl-sample-*.tmp")), [])

    def check_original(self, name):
        source = self.source(name)
        original = source.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), CLIPS[name])
        self.assertEqual(struct.unpack_from("<I", original, 4)[0], fnv32(original[8:]))
        # A Unicode filename also checks wide Windows path handling.
        output = self.folder / f"动画-{name}.poses"
        result = self.run_sampler(source, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["inputSha256"], CLIPS[name])
        self.assertEqual(report["validationScope"], "sha256-pinned-original-clips-only")
        self.assertEqual(report["clipName"], name + ".acl")
        data = output.read_bytes()
        signature, bones, samples, rate = struct.unpack_from("<8sIIf", data)
        self.assertEqual(signature, b"HCZPOSE1")
        self.assertEqual(bones, struct.unpack_from("<H", original, 16)[0])
        self.assertEqual(samples, struct.unpack_from("<I", original, 28)[0])
        self.assertEqual(rate, struct.unpack_from("<f", original, 32)[0])
        self.assertEqual(len(data), 20 + bones * samples * 40)
        self.assertEqual((bones, samples), (report["bones"], report["samples"]))
        for transform in struct.iter_unpack("<10f", memoryview(data)[20:]):
            self.assertTrue(all(math.isfinite(value) for value in transform))
            self.assertLess(abs(sum(value * value for value in transform[:4]) - 1), .001)
        # Deterministic output and replacement of an existing artifact.
        output.write_bytes(b"previous artifact")
        second = self.run_sampler(source, output)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(output.read_bytes(), data)
        self.assertEqual(json.loads(second.stdout), report)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), CLIPS[name])
        self.assert_no_temporary_output()

    def test_stand_idle_decodes_deterministically(self):
        self.check_original("stand_idle")

    def test_skin_decodes_deterministically(self):
        self.check_original("skin")

    def assert_unrecognized_rejected(self, modified):
        modified = with_valid_fnv(modified)
        self.assertEqual(struct.unpack_from("<I", modified, 4)[0], fnv32(modified[8:]))
        source = self.folder / "unrecognized.acl"
        source.write_bytes(modified)
        output = self.folder / "preserved.poses"
        output.write_bytes(b"previous artifact must survive")
        result = self.run_sampler(source, output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("unsupported ACL SHA-256", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(output.read_bytes(), b"previous artifact must survive")
        self.assert_no_temporary_output()

    def test_rehashed_internal_offset_corruption_is_rejected(self):
        data = bytearray(self.source().read_bytes())
        segments = 16 + struct.unpack_from("<H", data, 36)[0]
        # Removing the format array previously passed the shallow offset check.
        struct.pack_into("<I", data, segments + 8, 0xffffffff)
        self.assert_unrecognized_rejected(data)

    def test_rehashed_invalid_bitrate_is_rejected(self):
        data = bytearray(self.source().read_bytes())
        segments = 16 + struct.unpack_from("<H", data, 36)[0]
        formats = 16 + struct.unpack_from("<I", data, segments + 8)[0]
        self.assertLess(formats, len(data))
        data[formats] = 255  # ACL valid rate indexes are 0..18.
        self.assert_unrecognized_rejected(data)

    def test_unknown_but_structurally_unchanged_bytes_are_rejected(self):
        data = bytearray(self.source().read_bytes())
        data[-1] ^= 1
        self.assert_unrecognized_rejected(data)

    def test_same_file_is_rejected_without_modification(self):
        source = self.folder / "same.acl"
        data = self.source().read_bytes()
        source.write_bytes(data)
        result = self.run_sampler(source, source)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("same file", result.stderr)
        self.assertEqual(source.read_bytes(), data)
        self.assert_no_temporary_output()

    def test_hardlink_to_input_is_rejected_without_modification(self):
        source = self.folder / "original.acl"
        data = self.source().read_bytes()
        source.write_bytes(data)
        output = self.folder / "alias.poses"
        os.link(source, output)
        result = self.run_sampler(source, output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("same file", result.stderr)
        self.assertEqual(source.read_bytes(), data)
        self.assertEqual(output.read_bytes(), data)
        self.assert_no_temporary_output()

    def test_publication_failure_preserves_destination_and_cleans_temp(self):
        output = self.folder / "existing-directory.poses"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_bytes(b"preserve directory")
        result = self.run_sampler(self.source(), output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("atomic output replacement failed", result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"preserve directory")
        self.assertEqual(result.stdout, "")
        self.assert_no_temporary_output()

    def test_truncation_does_not_clobber_existing_output(self):
        source = self.folder / "truncated.acl"
        source.write_bytes(self.source().read_bytes()[:24])
        output = self.folder / "preserved.poses"
        output.write_bytes(b"good artifact")
        result = self.run_sampler(source, output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("input size outside bounds", result.stderr)
        self.assertEqual(output.read_bytes(), b"good artifact")
        self.assert_no_temporary_output()


if __name__ == "__main__":
    unittest.main()
