"""Validate hostile KTX boundaries and real extracted texture payloads."""
import json
import pathlib
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from decode_ktx import IDENTIFIER, parse_ktx, raw_astc


def sample_folder():
    reproducible = ROOT / "analysis/assets/texture-samples"
    return reproducible if reproducible.is_dir() else ROOT / "analysis/assets/portability"


def fixture(*, endian="<", width=4, height=4, faces=1, mips=1, metadata=b"", internal=0x93B0):
    header = IDENTIFIER + struct.pack(endian + "13I", 0x04030201, 0, 1, 0,
                                      internal, 0x1908, width, height, 0, 0,
                                      faces, mips, len(metadata))
    levels = b""
    for mip in range(mips or 1):
        size = ((max(1, width >> mip) + 3) // 4) * ((max(1, height >> mip) + 3) // 4) * 16
        levels += struct.pack(endian + "I", size)
        levels += b"".join(bytes([mip * 6 + face]) * size for face in range(faces))
    return header + metadata + levels


def replace(data, offset, value):
    result = bytearray(data)
    struct.pack_into("<I", result, offset, value)
    return bytes(result)


class KtxBounds(unittest.TestCase):
    def test_both_endian_headers_and_unchanged_compressed_bytes(self):
        for endian in ("<", ">"):
            data = fixture(endian=endian, faces=6, mips=3)
            info = parse_ktx(data)
            raw = raw_astc(data, info, 2, 5)
            self.assertEqual(raw[:16], b"\x13\xab\xa1\x5c\x04\x04\x01\x01\x00\x00\x01\x00\x00\x01\x00\x00")
            self.assertEqual(raw[16:], bytes([17]) * 16)

    def test_non_power_of_two_size_and_generated_mips(self):
        info = parse_ktx(fixture(width=7, height=5, mips=0))
        self.assertEqual(info["levels"][0]["image_size"], 64)
        self.assertTrue(info["generate_mipmaps"])
        self.assertEqual(info["mip_count"], 1)

    def test_rejects_all_truncations_and_trailing_bytes(self):
        data = fixture(faces=6, mips=3)
        for cut in range(len(data)):
            with self.subTest(cut=cut), self.assertRaises(ValueError):
                parse_ktx(data[:cut])
        with self.assertRaises(ValueError):
            parse_ktx(data + b"extra")

    def test_rejects_bad_size_topology_and_resource_exhaustion(self):
        data = fixture()
        cases = [(12, 0), (16, 1), (20, 4), (24, 0x1908), (28, 0),
                 (36, 0), (36, 0xffffffff), (40, 0), (44, 1), (48, 1),
                 (52, 2), (56, 99), (60, 0xffffffff), (64, 17)]
        for offset, value in cases:
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                parse_ktx(replace(data, offset, value))
        with self.assertRaises(ValueError):
            parse_ktx(fixture(width=4, height=8, faces=6))

    def test_metadata_keys_values_and_alignment(self):
        raw = b"KTXorientation\x00S=r,T=d\x00"
        entry = struct.pack("<I", len(raw)) + raw + b"\x00" * (-len(raw) % 4)
        info = parse_ktx(fixture(metadata=entry))
        self.assertEqual(info["metadata"][0]["text"], "S=r,T=d")
        self.assertFalse(info["orientation_changed"])
        malformed = (b"\xff\xff\xff\xff", b"\x00\x00\x00\x00", b"\x04\x00\x00\x00abcd")
        for metadata in malformed:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                parse_ktx(fixture(metadata=metadata))

    def test_profile_warning_and_requested_level_bounds(self):
        data = fixture(internal=0x93D0)
        info = parse_ktx(data)
        self.assertEqual(info["profile"], "srgb")
        self.assertEqual(info["warnings"], [])
        self.assertEqual(len(parse_ktx(replace(data, 32, 0x93D0))["warnings"]), 1)
        for mip, face in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            with self.subTest(mip=mip, face=face), self.assertRaises(ValueError):
                raw_astc(data, info, mip, face)


class ShippedTextures(unittest.TestCase):
    def test_actual_sample_lengths_and_provenance_hashes(self):
        from decode_ktx import sha256
        folder = sample_folder()
        if not (folder / "resource_samples.json").is_file():
            self.skipTest("requires extracted APK evidence")
        entries = json.loads((folder / "resource_samples.json").read_text(encoding="utf-8"))
        samples = [e for e in entries if e.get("kind") == "KTX1" and "sample_path" in e]
        self.assertGreaterEqual(len(samples), 7)
        for sample in samples:
            with self.subTest(member=sample["member"], index=sample["index"]):
                data = (ROOT / sample["sample_path"].replace("\\", "/")).read_bytes()
                self.assertEqual(sha256(data), sample["sha256"])
                info = parse_ktx(data)
                for mip in range(info["mip_count"]):
                    for face in range(info["faces"]):
                        self.assertEqual(len(raw_astc(data, info, mip, face)),
                                         16 + info["levels"][mip]["image_size"])

    def test_exported_payload_decodes_with_official_astcenc(self):
        from decode_ktx import DEFAULT_DECODER, DEFAULT_INSPECTOR, convert
        source = sample_folder() / "uires.03481.KTX1.bin"
        if not source.is_file() or not DEFAULT_DECODER.is_file() or not DEFAULT_INSPECTOR.is_file():
            self.skipTest("requires extracted APK sample and pinned ASTC runtimes")
        # Regression against a real 990x820 ASTC 8x5 portrait. An external
        # decoder independently checks the ASTC container and block payload.
        with tempfile.TemporaryDirectory() as directory:
            result = convert([source], directory, DEFAULT_DECODER,
                             provenance_path=source.parent / "resource_samples.json")
            texture = result["textures"][0]
            image = texture["outputs"][0]
            self.assertEqual(texture["source_sha256"],
                             "c6557b5b2a4e64ad4d01f93006d92f74bb5dbad794d5f9c03b7347614f2d38e1")
            self.assertEqual((image["width"], image["height"]), (990, 820))
            self.assertEqual(image["rgba_sha256"],
                             "5f5362f6e6c241116e1233f551859b48038a7b936b06e8bec1f7da049837e04d")
            self.assertEqual(image["channel_extrema_rgba"][3], (0, 255))
            self.assertEqual(texture["block_validation"]["hdr_blocks"], 0)

    def test_converter_refuses_valid_hdr_and_invalid_astc_before_writing_png(self):
        from decode_ktx import DEFAULT_DECODER, DEFAULT_INSPECTOR, convert
        if not DEFAULT_DECODER.is_file() or not DEFAULT_INSPECTOR.is_file():
            self.skipTest("requires pinned ASTC runtimes")
        # HDR void-extent white is a valid ASTC block; astcenc -dl alone returns
        # success with an error-color pixel. The all-zero block is illegal.
        blocks = (bytes.fromhex("fcffffffffffffff003c003c003c003c"), b"\x00" * 16)
        for block in blocks:
            with self.subTest(block=block.hex()), tempfile.TemporaryDirectory() as directory:
                source = pathlib.Path(directory) / "unsupported.ktx"
                source.write_bytes(fixture()[:-16] + block)
                output = pathlib.Path(directory) / "output"
                with self.assertRaisesRegex(ValueError, "HDR or invalid ASTC"):
                    convert([source], output, DEFAULT_DECODER)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
