"""NXPK format boundaries and immutable APK evidence; standard library only.

These tests never load a Python code object or execute APK bytecode. Synthetic
archives describe the observed wire layout; APK tests read the original member.
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import struct
import unittest
import zipfile
import zlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("extract_npk", ROOT / "tools" / "extract_npk.py")
NPK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NPK)


def archive(payload=b"payload", *, compression=0, encryption=0, original_size=None, stored=None):
    """Build one record directly from the observed 24-byte/28-byte layout."""
    if stored is None:
        stored = zlib.compress(payload) if compression == 1 else payload
    if original_size is None:
        original_size = len(payload)
    index = 24 + len(stored)
    header = struct.pack("<4s5I", b"NXPK", 1, 0, 0, 1, index)
    record = struct.pack("<6I2H", 0x12345678, 24, len(stored), original_size, 0, 0,
                         compression, encryption)
    return header + stored + record


def change_u32(data, offset, value):
    changed = bytearray(data)
    struct.pack_into("<I", changed, offset, value)
    return bytes(changed)


def extract_one(data):
    _, entries = NPK.parse_npk(data)
    return NPK.decode_entry(data, entries[0])


class NpkBoundaryTests(unittest.TestCase):
    def test_plain_and_compressed_payloads_round_trip(self):
        for payload in (b"", b"payload", bytes(range(256))):
            for compression in (0, 1):
                with self.subTest(size=len(payload), compression=compression):
                    self.assertEqual(extract_one(archive(payload, compression=compression)), payload)

    def test_truncated_headers_and_index_are_rejected(self):
        data = archive()
        for cut in (0, 4, 23, 24, len(data) - 1):
            with self.subTest(cut=cut), self.assertRaises(ValueError):
                NPK.parse_npk(data[:cut])

    def test_non_nxpk_and_index_bounds_are_rejected(self):
        data = archive()
        cases = {
            "magic": b"NPK!" + data[4:],
            "index_inside_header": change_u32(data, 20, 20),
            "index_past_file": change_u32(data, 20, len(data) + 1),
            "missing_record": change_u32(data, 4, 2),
            "unbounded_count": change_u32(data, 4, 0xFFFFFFFF),
            "trailing_archive_data": data + b"extra",
        }
        for reason, value in cases.items():
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                NPK.parse_npk(value)

    def test_entry_cannot_read_header_or_index(self):
        data = archive()
        index = struct.unpack_from("<I", data, 20)[0]
        cases = {
            "offset_in_header": change_u32(data, index + 4, 23),
            "offset_at_index": change_u32(data, index + 4, index),
            "payload_crosses_index": change_u32(data, index + 8, 8),
            "oversized_payload": change_u32(data, index + 8, 0xFFFFFFFF),
        }
        for reason, value in cases.items():
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                NPK.parse_npk(value)

    def test_declared_uncompressed_length_must_match(self):
        for compression in (0, 1):
            for declared in (0, 6, 8):
                with self.subTest(compression=compression, declared=declared):
                    with self.assertRaises(ValueError):
                        extract_one(archive(b"payload", compression=compression, original_size=declared))

    def test_inflation_past_declared_length_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_one(archive(b"A" * 4096, compression=1, original_size=16))

    def test_decoded_size_budget_is_enforced(self):
        data = archive(b"A" * 32, compression=1)
        _, entries = NPK.parse_npk(data)
        self.assertEqual(NPK.decode_entry(data, entries[0], max_decoded_bytes=32), b"A" * 32)
        with self.assertRaises(ValueError):
            NPK.decode_entry(data, entries[0], max_decoded_bytes=31)
        with self.assertRaises(ValueError):
            extract_one(archive(compression=1, original_size=0xFFFFFFFF))

    def test_invalid_and_truncated_compressed_streams_are_rejected(self):
        valid = zlib.compress(b"payload")
        for stored in (b"invalid", valid[:-1], valid[:-4], b""):
            with self.subTest(stored=stored.hex()), self.assertRaises((ValueError, zlib.error)):
                extract_one(archive(compression=1, stored=stored))

    def test_compressed_entry_must_consume_its_whole_stored_region(self):
        for suffix in (b"garbage", zlib.compress(b"second stream")):
            with self.subTest(suffix=suffix.hex()), self.assertRaises(ValueError):
                extract_one(archive(compression=1, stored=zlib.compress(b"payload") + suffix))

    def test_unknown_encoding_flags_are_rejected(self):
        for flags in ({"compression": 2}, {"encryption": 1}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                extract_one(archive(**flags))


class MarshalBoundaryTests(unittest.TestCase):
    def test_truncated_values_and_invalid_lengths_are_rejected(self):
        cases = [b"", b"i\x00", b"s" + struct.pack("<i", 4) + b"abc",
                 b"s" + struct.pack("<i", -1), b"(" + struct.pack("<i", -1),
                 b"c" + bytes(15), b"{" + b"N", b"?"]
        for value in cases:
            with self.subTest(data=value.hex()), self.assertRaises(ValueError):
                NPK.Marshal2(value).obj()

    def test_string_reference_must_be_nonnegative_and_defined(self):
        # A two-element tuple: interned byte string followed by its reference.
        prefix = b"(" + struct.pack("<i", 2) + b"t" + struct.pack("<i", 3) + b"abc"
        self.assertEqual(NPK.Marshal2(prefix + b"R" + struct.pack("<i", 0)).obj(), [b"abc", b"abc"])
        for reference in (-1, 1, 0x7FFFFFFF):
            with self.subTest(reference=reference), self.assertRaises((ValueError, IndexError)):
                NPK.Marshal2(prefix + b"R" + struct.pack("<i", reference)).obj()

    def test_excessive_nested_collections_are_rejected(self):
        data = (b"(" + struct.pack("<i", 1)) * 102 + b"N"
        with self.assertRaises(ValueError):
            NPK.Marshal2(data).obj()


@unittest.skipUnless(NPK.APK.is_file(), "original APK is not present")
class ActualApkEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(NPK.APK) as apk:
            cls.data = apk.read("assets/script.npk")
        _, cls.entries = NPK.parse_npk(cls.data)

    def test_two_plain_redirect_modules_are_identical_and_fully_consumed(self):
        records = [entry for entry in self.entries if entry["name_hash"] == 0xFB54F059]
        self.assertEqual(len(records), 2)
        objects = []
        for entry in records:
            with self.subTest(entry=entry["index"]):
                payload = NPK.decode_entry(self.data, entry)
                self.assertEqual(len(payload), 4880)
                self.assertEqual(hashlib.sha256(payload).hexdigest(),
                                 "6325771b23f68808b849ffe06f85bb67b2be75584d035750200357b3f620e353")
                reader = NPK.Marshal2(payload)
                module = reader.obj()
                self.assertEqual(reader.pos, len(payload))
                self.assertIsInstance(module, dict)
                self.assertEqual(module["type"], "code")
                self.assertEqual(module["filename"], b"redirect.py")
                self.assertEqual(module["name"], b"<module>")
                self.assertEqual(module["argcount"], 0)
                self.assertEqual(module["firstlineno"], 2)
                self.assertIsInstance(module["bytecode"], bytes)
                functions = {item["name"] for item in module["consts"]
                             if isinstance(item, dict) and item.get("type") == "code"}
                self.assertTrue({b"init_rotor", b"_reverse_string", b"NpkImporter"} <= functions)
                objects.append(module)
        self.assertEqual(objects[0], objects[1])

    def test_truncated_real_module_is_not_accepted(self):
        record = next(entry for entry in self.entries if entry["name_hash"] == 0xFB54F059)
        payload = NPK.decode_entry(self.data, record)
        for cut in (1, 16, 100, len(payload) - 1):
            with self.subTest(cut=cut), self.assertRaises((ValueError, IndexError)):
                NPK.Marshal2(payload[:cut]).obj()


if __name__ == "__main__":
    unittest.main()
