"""Check the original GIM socket, independently from the exported skin."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from recover_elsa_entrance import source_effect_binding
from export_elsa_model import split_glb


@unittest.skipUnless((ROOT/'analysis/battle-visual/scene-export/source/File_26.gim').is_file(), 'requires extracted original GIM')
class EntranceSourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT/'analysis/battle-visual/scene-export/source/File_26.gim').read_bytes()

    def test_binding_is_authored_socket_without_bone(self):
        row = source_effect_binding(self.raw)
        self.assertEqual(row['socketXmlTag'], 'Socket_2')
        self.assertEqual(row['socket']['Name'], 'fx_center')
        self.assertEqual(row['socket']['BindType'], '7')
        self.assertIsNone(row['boneNameAuthored'])
        self.assertTrue(row['identityMatrixLiteral'])
        self.assertFalse(row['runtimeBindingVerified'])
        active = [x for x in row['boundObjects'] if x['Name'] == row['trigger']['ObjectFileName']]
        self.assertEqual(active, [{'Name': 'effects/player/001/fight_idle_show_chuchang.sfx', 'Active': 'true'}])
        json.dumps(row, allow_nan=False)

    def test_changed_socket_source_is_rejected_before_interpretation(self):
        with self.assertRaisesRegex(ValueError, 'GIM identity changed'):
            source_effect_binding(self.raw.replace(b'fx_center', b'fake_bone'))

    @unittest.skipUnless((ROOT/'analysis/battle-visual/entrance/elsa_entrance.glb').is_file(), 'requires original entrance conversion')
    def test_socket_is_not_misrepresented_as_a_skin_joint(self):
        doc, _ = split_glb((ROOT/'analysis/battle-visual/entrance/elsa_entrance.glb').read_bytes())
        names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
        self.assertEqual(len(names), 180)
        self.assertNotIn(source_effect_binding(self.raw)['socket']['Name'], names)


if __name__ == '__main__':
    unittest.main()
