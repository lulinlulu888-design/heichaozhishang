"""Guard the narrow source exception and byte-preserving slash export."""
import copy
import json
from pathlib import Path
import unittest

from export_elsa_model import bind_materials, parse_materials, split_glb, pack_glb
from export_elsa_normal_slash import (EFFECTS, MESH, VARIANTS, bind_daoguang_full_ring,
                                     verify_glb_arrays, xml_tree)
from export_neox_gltf import encode_glb
from inspect_neox_model import ModelError, parse_model


class OriginalSlashExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = EFFECTS / 'bindings.json'
        if not manifest.exists():
            raise unittest.SkipTest('Local extracted APK evidence is required')
        report = json.loads(manifest.read_text('utf8'))
        cls.sources = {x['source']['logical_path']: x['source'] for x in report['files']}
        cls.raw = cls.read(MESH)
        cls.model = parse_model(cls.raw)

    @classmethod
    def read(cls, logical):
        return Path(cls.sources[logical]['sample_path']).read_bytes()

    def inputs(self, logical=None):
        logical = logical or next(iter(VARIANTS))
        return self.read(logical), parse_materials(self.read(logical[:-4] + '.mtg'), expected_slots=1)

    def test_only_known_full_ring_variants_use_conservative_bounds(self):
        for logical in VARIANTS:
            gim, materials = self.inputs(logical)
            with self.assertRaisesRegex(ModelError, 'independent bounds mismatch'):
                bind_materials(self.model, gim, materials)
            bound = bind_daoguang_full_ring(self.model, gim, materials)[0]['bounds_validation']
            self.assertTrue(bound['allVerticesContained'])
            self.assertFalse(bound['geometryRescaled'])
            self.assertAlmostEqual(bound['radiusTimesCosHalfStep'], bound['meshAabb']['max'][0], places=4)
        # The implicit base GIM is deliberately NOT covered by this exception.
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(self.model, self.read('effects/modeleffect/char/001/daoguang_01.gim'), materials)

    def test_changed_gim_mesh_identity_or_material_association_is_rejected(self):
        gim, materials = self.inputs()
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(self.model, gim.replace(b'46.7992', b'60.0000'), materials)
        model = copy.deepcopy(self.model)
        model['sha256'] = '0' * 64
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(model, gim, materials)
        materials[0]['name'] = 'Unrelated mesh material'
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(self.model, gim, materials)

    def test_decoded_geometry_cannot_escape_or_silently_rescale(self):
        gim, materials = self.inputs()
        model = copy.deepcopy(self.model)
        model['positions'][0] = (48.0, 0.0, 0.0)
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(model, gim, materials)
        model = copy.deepcopy(self.model)
        model['positions'] = [tuple(v * 1.002 for v in p) for p in model['positions']]
        with self.assertRaises(ModelError):
            bind_daoguang_full_ring(model, gim, materials)

    def test_glb_roundtrip_compares_source_bytes_and_detects_uv_mutation(self):
        blob, _, _ = encode_glb(self.model, 'test')
        self.assertEqual(len(verify_glb_arrays(blob, self.raw, self.model)), 4)
        doc, binary = split_glb(blob)
        uv = doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0']
        offset = doc['bufferViews'][doc['accessors'][uv]['bufferView']]['byteOffset']
        damaged = bytearray(binary)
        damaged[offset] ^= 1
        with self.assertRaisesRegex(ModelError, 'TEXCOORD_0'):
            verify_glb_arrays(pack_glb(doc, damaged), self.raw, self.model)
        doc['nodes'][0]['scale'] = [1.003, 1, 1.003]
        with self.assertRaisesRegex(ModelError, 'node transform'):
            verify_glb_arrays(pack_glb(doc, binary), self.raw, self.model)

    def test_recipe_preserves_order_repeated_nodes_and_raw_curve_enums(self):
        root, nodes = xml_tree(b'<FxGroup>\n<Model Name="a"/><Model Name="b"><ScaleFrame ChangeType="4"><Frame Time="0.5" Value="0.52"/></ScaleFrame></Model></FxGroup>')
        self.assertEqual([x['attributes']['Name'] for x in root['children']], ['a', 'b'])
        self.assertEqual(nodes['/FxGroup[1]/Model[2]']['line'], 2)
        self.assertEqual(nodes['/FxGroup[1]/Model[2]/ScaleFrame[1]']['attributes']['ChangeType'], '4')


if __name__ == '__main__':
    unittest.main()
