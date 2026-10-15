import unittest

from PIL import Image
from verify_scene_reflection_samples import center_rgb, compare


class ReflectionSamplesTest(unittest.TestCase):
    def test_even_center_averages_four_texels_and_single_texel_is_exact(self):
        im = Image.new('RGB', (2,2))
        for xy, color in zip(((0,0),(1,0),(0,1),(1,1)), ((0,0,0),(255,0,0),(0,255,0),(0,0,255))):
            im.putpixel(xy, color)
        self.assertEqual(center_rgb(im), [.25,.25,.25])
        self.assertEqual(center_rgb(Image.new('RGB',(1,1),(255,0,0))), [1,0,0])

    def test_missing_and_duplicate_samples_cannot_pass(self):
        expected = {(0,0):[1,0,0], (0,1):[0,1,0]}
        row = dict(face=0,mip=0,rgb=[1,0,0])
        for samples in ([row], [row,row]):
            with self.assertRaises(ValueError):
                compare(samples, expected)

    def test_wrong_mip_sample_and_nonfinite_values_fail(self):
        expected = {(0,0):[1,0,0], (0,1):[0,1,0]}
        rows = [dict(face=0,mip=0,rgb=[1,0,0]),dict(face=0,mip=1,rgb=[1,0,0])]
        self.assertFalse(compare(rows, expected)['passed'])
        rows[1]['rgb'] = [float('nan'),0,0]
        with self.assertRaises(ValueError):
            compare(rows, expected)


if __name__ == '__main__':
    unittest.main()
