"""Reject malformed record boundaries before trusting bank scan coverage."""
import struct
import unittest

from scan_enemy_audio_banks import objects
from inspect_enemy_audio import chunks


class AudioBankBounds(unittest.TestCase):
    def test_hirc_record_and_offset(self):
        raw = struct.pack('<IBII', 1, 4, 6, 1234) + b'ab'
        self.assertEqual(objects(raw), [dict(type=4, id=1234, offset=4, bytes=11)])

    def test_invalid_hirc_boundaries(self):
        for raw in (b'', struct.pack('<I', 100001), struct.pack('<I', 1),
                    struct.pack('<IBII', 1, 4, 3, 1),
                    struct.pack('<IBII', 1, 4, 9, 1), struct.pack('<I', 0)+b'x'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                objects(raw)

    def test_chunk_payload_offset(self):
        self.assertEqual(chunks(b'BKHD'+struct.pack('<I', 3)+b'abc'), {b'BKHD': (8,b'abc')})

    def test_invalid_chunks(self):
        for raw in (b'x', b'DATA'+struct.pack('<I', 5)+b'a',
                    b'DATA'+struct.pack('<I', 0)+b'DATA'+struct.pack('<I', 0)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                chunks(raw)


if __name__ == '__main__':
    unittest.main()
