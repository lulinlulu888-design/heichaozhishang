"""Regression evidence for path hashing, rooted lookup, and VT config bounds."""
from pathlib import Path
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from neox_resource_paths import (string_id_legacy, resource_hash, script_path,
                                 verify_scripts, lookup, lookup_logical, parse_vt_config)


class ResourcePaths(unittest.TestCase):
    def test_actual_script_corpus(self):
        report = verify_scripts(ROOT/'analysis/assets/decoded/script/index.json')
        self.assertEqual((report['count'], report['matched'], report['unique_filenames']),
                         (9698, 9698, 9697))

    def test_fixed_archive_vectors(self):
        self.assertEqual(string_id_legacy(b'redirect.nxs'), 0xfb54f059)
        self.assertEqual(string_id_legacy(b'json\\__init__.nxs'), 0x0004cc2d)
        self.assertEqual(string_id_legacy(b'rpc.nxs'), 0x275114af)
        self.assertEqual(resource_hash('CommonRes/BigSan/Char_detail/img_char_photo_elsa.pkm'), 0xdfe85ea9)
        self.assertEqual(resource_hash('player/ailisha/ailisha_yangcheng.mesh'), 0xce7a9e54)

    def test_raw_cstring_versus_path_api(self):
        self.assertEqual(string_id_legacy(b'redirect.nxs\0ignored'), 0xfb54f059)
        with self.assertRaises(ValueError):
            resource_hash('redirect.nxs\0ignored')
        with self.assertRaises(ValueError):
            resource_hash('')
        self.assertNotEqual(resource_hash('Foo/bar.nxs'), resource_hash('foo/bar.nxs'))
        self.assertEqual(resource_hash('Foo/bar.nxs'), resource_hash('Foo\\bar.nxs'))

    def test_observed_script_roots(self):
        self.assertEqual(script_path('lib\\json\\__init__.py'), 'json\\__init__.nxs')
        self.assertEqual(script_path('engine\\common\\rpc.py'), 'rpc.nxs')
        self.assertEqual(script_path('helper\\cocosvt.py'), 'helper\\cocosvt.nxs')
        with self.assertRaises(ValueError):
            script_path('example.bin')

    def test_do_not_hide_hash_collisions(self):
        value = resource_hash('test.png')
        catalogue = [{'member': 'assets/res/a.npk', 'entries': [
            {'index': 1, 'name_hash': value}, {'index': 2, 'name_hash': value}]},
            {'member': 'assets/res/b.npk', 'entries': [{'index': 3, 'name_hash': value}]}]
        self.assertEqual(len(lookup(catalogue, 'test.png')), 3)
        self.assertEqual([r['index'] for r in lookup_logical(catalogue, 'a/test.png')], [1, 2])

    def test_six_actual_portrait_paths(self):
        catalogue = json.loads((ROOT/'analysis/resource-mapping/npk-indices.json').read_text('utf8'))
        rows = json.loads((ROOT/'analysis/resource-mapping/characters-path-matches.json').read_text('utf8'))
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertEqual(lookup_logical(catalogue, row['archive_logical_path']), row['matches'])
            self.assertEqual(len(row['matches']), 1)

    def test_vt_complete_parse(self):
        data = (ROOT/'analysis/resource-mapping/vt_config.jsondata').read_bytes()
        result = parse_vt_config(data)
        self.assertEqual([len(result[k]) for k in ('plistToPageID', 'pngsToPageID', 'fullPathToPng')],
                         [47, 5894, 5894])
        for malformed in (data[:-1], data+b'\0', struct.pack('<I', 2)+data[4:],
                          data[:4]+struct.pack('<I', 100001)+data[8:],
                          data[:8]+struct.pack('<I', 3)+data[12:]):
            with self.assertRaises(ValueError):
                parse_vt_config(malformed)

    def test_portrait_pixel_provenance(self):
        import hashlib
        from PIL import Image
        rows = json.loads((ROOT/'analysis/resource-mapping/characters/portraits.json').read_text('utf8'))
        self.assertEqual({r['character_id'] for r in rows}, {1, 2, 3})
        for row in rows:
            png = ROOT/row['png']
            self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), row['png_sha256'])
            with Image.open(png) as image:
                self.assertEqual(image.size, (990, 820))
                self.assertEqual(image.getchannel('A').getextrema(), (0, 255))
                self.assertEqual(hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest(), row['rgba_sha256'])


if __name__ == '__main__':
    unittest.main()
