"""DDS byte layout checks using asymmetric face/mip colors."""
import struct
import unittest

from PIL import Image
from prepare_scene_reflection_dds import pack_cube


class CubeDDSTest(unittest.TestCase):
    def test_face_major_complete_mips_and_linear_format(self):
        levels = [[Image.new('RGBA', (size, size), (face * 31, mip * 79, 17, 255))
                   for face in range(6)] for mip, size in enumerate((4, 2, 1))]
        data = pack_cube(levels)
        self.assertEqual(data[:4], b'DDS ')
        self.assertEqual(struct.unpack_from('<I', data, 4)[0], 124)
        self.assertEqual(struct.unpack_from('<I', data, 28)[0], 3)
        self.assertEqual(data[84:88], b'DX10')
        self.assertEqual(struct.unpack_from('<5I', data, 128), (28, 3, 4, 1, 0))
        self.assertEqual(struct.unpack_from('<I', data, 112)[0], 0xFE00)
        offset = 148
        for face in range(6):
            for mip, size in enumerate((4, 2, 1)):
                length = size * size * 4
                expected = bytes((face * 31, mip * 79, 17, 255)) * (size * size)
                self.assertEqual(data[offset:offset+length], expected)
                offset += length
        self.assertEqual(offset, len(data))

    def test_incomplete_and_nonsquare_input_rejected(self):
        with self.assertRaises(ValueError):
            pack_cube([[Image.new('RGBA', (4, 4))] * 6])
        with self.assertRaises(ValueError):
            pack_cube([[Image.new('RGBA', (2, 3))] * 6, [Image.new('RGBA', (1, 1))] * 6])
        with self.assertRaises(ValueError):
            pack_cube([[Image.new('RGBA', (1, 1))] * 5])


if __name__ == '__main__':
    unittest.main()
