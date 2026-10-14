"""Check block semantics through the pinned official ARM implementation.

Run tools/setup_astc_inspector.py first. Fixtures are raw compressed blocks,
not an assertion about displayed pixel color or reconstructed game materials.
"""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "tools/runtime/astc-inspector-5.7.0/build/Release/astc-block-info.exe"
LDR_CONSTANT = bytes.fromhex("fcfdffffffffffff000000000000ffff")
HDR_CONSTANT = bytes.fromhex("fcffffffffffffff003c003c003c003c")
# ARM astcenc 5.7.0 official Windows SSE2 encoder, -ch gradient.hdr out.astc
# 4x4 -fastest -silent. Source RGBE recipe and hashes: docs/astc-validation.md.
# Endpoint mode 11 in two partitions; not a void-extent/constant block.
HDR_GRADIENT = bytes.fromhex("510802b6c882e0ce8a2c116c4d7fbd01")
INVALID = bytes(16)


def raw_astc(blocks, width=4, height=4, block=(4, 4)):
    header = b"\x13\xab\xa1\x5c" + bytes((*block, 1))
    header += b"".join(n.to_bytes(3, "little") for n in (width, height, 1))
    return header + b"".join(blocks)


@unittest.skipUnless(INSPECTOR.is_file(), "requires tools/setup_astc_inspector.py")
class AstcInspector(unittest.TestCase):
    def run_inspector(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "fixture.astc"
            path.write_bytes(data)
            return subprocess.run([str(INSPECTOR), str(path)], capture_output=True,
                                  text=True, timeout=30)

    def inspect(self, blocks, **kwargs):
        result = self.run_inspector(raw_astc(blocks, **kwargs))
        self.assertIn(result.returncode, (0, 2), result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode == 0, report["ldr_compatible"])
        self.assertEqual(report["block_count"],
                         report["ldr_blocks"] + report["hdr_blocks"] + report["error_blocks"])
        return report

    def test_ldr_constant_is_accepted(self):
        report = self.inspect([LDR_CONSTANT])
        self.assertTrue(report["ldr_compatible"])
        self.assertEqual(report["ldr_blocks"], 1)
        self.assertEqual(report["constant_ldr_blocks"], 1)
        self.assertEqual(report["first_problem_blocks"], [])

    def test_hdr_void_extent_is_rejected(self):
        report = self.inspect([HDR_CONSTANT])
        self.assertFalse(report["ldr_compatible"])
        self.assertEqual(report["hdr_blocks"], 1)
        self.assertEqual(report["constant_hdr_blocks"], 1)
        self.assertEqual(report["error_blocks"], 0)

    def test_official_nonconstant_hdr_is_rejected(self):
        report = self.inspect([HDR_GRADIENT])
        self.assertFalse(report["ldr_compatible"])
        self.assertEqual(report["hdr_blocks"], 1)
        self.assertEqual(report["constant_hdr_blocks"], 0)
        self.assertEqual(report["error_blocks"], 0)
        self.assertEqual(report["endpoint_mode_partition_counts"][11], 2)
        self.assertFalse(report["first_problem_blocks"][0]["constant"])

    def test_error_block_is_rejected_without_pixel_decode(self):
        report = self.inspect([INVALID])
        self.assertFalse(report["ldr_compatible"])
        self.assertEqual(report["error_blocks"], 1)
        self.assertEqual(report["hdr_blocks"], 0)
        self.assertEqual(report["first_problem_blocks"][0]["classification"], "error")

    def test_invalid_void_extent_is_error_before_hdr_bit_check(self):
        # Clear one required reserved bit in the otherwise HDR constant block.
        block = bytearray(HDR_CONSTANT)
        block[1] &= ~4
        report = self.inspect([bytes(block)])
        self.assertEqual(report["error_blocks"], 1)
        self.assertEqual(report["hdr_blocks"], 0)
        self.assertEqual(report["constant_hdr_blocks"], 0)

    def test_mixed_blocks_report_exact_compressed_offsets(self):
        report = self.inspect([LDR_CONSTANT, HDR_GRADIENT, INVALID], width=12)
        self.assertEqual((report["ldr_blocks"], report["hdr_blocks"], report["error_blocks"]), (1, 1, 1))
        examples = report["first_problem_blocks"]
        self.assertEqual([e["block_index"] for e in examples], [1, 2])
        self.assertEqual([e["raw_astc_offset"] for e in examples], [32, 48])
        self.assertEqual([e["hex"] for e in examples], [HDR_GRADIENT.hex(), INVALID.hex()])

    def test_problem_details_are_bounded_but_counts_are_complete(self):
        report = self.inspect([INVALID] * 32, width=128)
        self.assertEqual(report["error_blocks"], 32)
        self.assertEqual(len(report["first_problem_blocks"]), 16)

    def test_incomplete_header_payload_and_trailing_data_are_rejected(self):
        good = raw_astc([LDR_CONSTANT])
        for bad in (b"", good[:15], good[:16], good[:-1], good + b"\x00",
                    b"bad!" + good[4:], raw_astc([LDR_CONSTANT], width=0),
                    raw_astc([LDR_CONSTANT], width=16385),
                    raw_astc([LDR_CONSTANT], block=(3, 3)),
                    good[:6] + b"\x02" + good[7:]):
            with self.subTest(data=bad.hex()):
                result = self.run_inspector(bad)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)

    def test_official_sample_evidence_is_all_ldr(self):
        folder = ROOT / "analysis/assets/converted-ktx"
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("requires original APK texture evidence")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inspected = 0
        for texture in manifest["textures"]:
            for output in texture["outputs"]:
                path = ROOT / output["astc"]
                with self.subTest(path=path.name):
                    result = self.run_inspector(path.read_bytes())
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report["hdr_blocks"], 0)
                    self.assertEqual(report["error_blocks"], 0)
                    self.assertEqual(report["width"], output["width"])
                    self.assertEqual(report["height"], output["height"])
                    inspected += 1
        self.assertGreater(inspected, 0)


if __name__ == "__main__":
    unittest.main()
