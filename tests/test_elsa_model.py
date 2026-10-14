"""Independent checks of the real, named Elsa model and material export."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from export_elsa_model import bind_materials, parse_materials, split_glb, assert_shader_evidence
from inspect_neox_model import ModelError, matrix_rows, multiply4, parse_model

OUT = ROOT/'analysis/elsa-model'


def values(doc, data, index):
    accessor = doc['accessors'][index]
    view = doc['bufferViews'][accessor['bufferView']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[accessor['type']]
    fmt = {5121: 'B', 5123: 'H', 5126: 'f'}[accessor['componentType']]
    record = struct.Struct('<'+fmt*width)
    start = view.get('byteOffset', 0)+accessor.get('byteOffset', 0)
    assert start % 4 == 0
    assert start+record.size*accessor['count'] <= view.get('byteOffset', 0)+view['byteLength'] <= len(data)
    return list(record.iter_unpack(data[start:start+record.size*accessor['count']]))


@unittest.skipUnless((OUT/'export-report.json').exists(), 'named Elsa export not generated')
class ElsaExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((OUT/'export-report.json').read_text('utf8'))
        cls.mesh = (OUT/'source/elsa-mesh.mesh').read_bytes()
        cls.model = parse_model(cls.mesh)
        cls.gim = (OUT/'source/elsa-gim.gim').read_bytes()
        cls.materials = parse_materials((OUT/'source/elsa-mtg.mtg').read_bytes())
        cls.glb = (OUT/'elsa-yangcheng.colour-reference.glb').read_bytes()
        cls.doc, cls.data = split_glb(cls.glb)

    def test_named_source_and_full_counts(self):
        self.assertEqual(hashlib.sha256(self.mesh).hexdigest(), '22677b92724bdc12c0e7aae0e8450a70602949f5f242dc1e965150cab316b618')
        m = self.model
        self.assertEqual((m['vertex_count'], m['triangle_count'], m['submesh_count'], len(m['bones'])), (19063, 29240, 9, 180))
        self.assertEqual(m['coverage_bytes'], len(self.mesh))
        self.assertEqual(len(self.glb), self.report['glb_bytes'])
        self.assertEqual(hashlib.sha256(self.glb).hexdigest(), self.report['glb_sha256'])
        self.assertLess(self.report['bind_validation']['max_bound_error'], 3e-6)

    def test_geometry_both_uv_sets_and_indices_are_identical(self):
        m = self.model
        for sub, primitive in zip(m['submeshes'], self.doc['meshes'][0]['primitives']):
            start, end = sub['vertex_start'], sub['vertex_start']+sub['vertex_count']
            for attribute, field in [('POSITION', 'positions'), ('NORMAL', 'normals')]:
                self.assertEqual(values(self.doc, self.data, primitive['attributes'][attribute]), m[field][start:end])
            self.assertEqual(len(sub['uvs']), 2)
            for c in range(2):
                self.assertEqual(values(self.doc, self.data, primitive['attributes'][f'TEXCOORD_{c}']), sub['uvs'][c])
            ix = [r[0]+start for r in values(self.doc, self.data, primitive['indices'])]
            first = sub['triangle_start']*3
            self.assertEqual(ix, m['indices'][first:first+sub['triangle_count']*3])

    def test_independent_gim_bounds_and_nonsequential_material_slots(self):
        rows = bind_materials(self.model, self.gim, self.materials)
        slots = [5, 7, 8, 6, 4, 3, 1, 2, 0]
        self.assertEqual([x['material_slot'] for x in rows], slots)
        self.assertEqual([x['material'] for x in self.doc['meshes'][0]['primitives']], slots)
        self.assertLess(max(x['bounds_max_error'] for x in rows), 8e-6)

    def test_wrong_submesh_or_material_binding_rejected(self):
        with self.assertRaisesRegex(ModelError, 'bounds mismatch'):
            bind_materials(self.model, self.gim.replace(b'0.446450', b'0.946450'), self.materials)
        with self.assertRaisesRegex(ModelError, 'material slot'):
            bind_materials(self.model, self.gim.replace(b'MtlIdx="5"', b'MtlIdx="99"'), self.materials)

    def test_all_vertices_rest_skinning_from_exported_nodes(self):
        d, b = self.doc, self.data
        parents = {ch: i for i, n in enumerate(d['nodes']) for ch in n.get('children', [])}
        worlds = {}
        identity = [[float(i == j) for j in range(4)] for i in range(4)]
        def world(i):
            if i not in worlds:
                node = d['nodes'][i]
                local = matrix_rows(node['matrix']) if 'matrix' in node else identity
                worlds[i] = multiply4(world(parents[i]), local) if i in parents else local
            return worlds[i]
        skin = d['skins'][0]
        ibm = values(d, b, skin['inverseBindMatrices'])
        matrices = [multiply4(world(node), matrix_rows(ibm[i])) for i, node in enumerate(skin['joints'])]
        error = 0.0
        for primitive in d['meshes'][0]['primitives']:
            attr = primitive['attributes']
            for p, joints, weights in zip(values(d, b, attr['POSITION']), values(d, b, attr['JOINTS_0']), values(d, b, attr['WEIGHTS_0'])):
                self.assertTrue(all(0 <= j < 180 for j in joints))
                self.assertAlmostEqual(sum(weights), 1, places=6)
                v = (*p, 1)
                posed = [sum(w*sum(matrices[j][r][k]*v[k] for k in range(4)) for j, w in zip(joints, weights)) for r in range(3)]
                error = max(error, *(abs(a-b) for a, b in zip(p, posed)))
        self.assertLess(error, 3e-6)

    def test_only_proven_colour_textures_and_eye_alpha(self):
        materials = self.doc['materials']
        self.assertEqual((len(materials), len(self.doc['images'])), (9, 7))
        self.assertEqual(materials[5]['alphaMode'], 'OPAQUE')
        self.assertEqual(materials[2]['pbrMetallicRoughness']['baseColorFactor'], [.392157, .368627, .392157, 1])
        for m in materials:
            self.assertEqual(m['extensions'], {'KHR_materials_unlit': {}})
            self.assertNotIn('normalTexture', m)
            self.assertNotIn('occlusionTexture', m)
            self.assertNotIn('metallicRoughnessTexture', m['pbrMetallicRoughness'])
            self.assertEqual(m['pbrMetallicRoughness']['baseColorTexture']['texCoord'], 0)
        self.assertEqual(materials[0]['alphaMode'], 'BLEND')
        self.assertEqual(materials[6]['alphaMode'], 'BLEND')
        self.assertEqual(self.report['character_local_unique_textures'], 20)
        self.assertEqual(self.report['total_unique_textures'], 22)
        assert_shader_evidence(OUT/'shader-evidence')

    def test_embedded_pngs_and_colour_profile_conversion(self):
        from PIL import Image
        import numpy as np
        for image in self.doc['images']:
            view = self.doc['bufferViews'][image['bufferView']]
            blob = self.data[view['byteOffset']:view['byteOffset']+view['byteLength']]
            self.assertEqual(blob[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(hashlib.sha256(blob).hexdigest(), image['extras']['pngSha256'])
        for record in self.report['decoded_colour_textures'].values():
            t = record['decoder_record']
            self.assertEqual(t['block_validation']['validated_mips'], t['texture']['mip_count'])
            if t['texture']['profile'] != 'linear':
                self.assertEqual(record['gltf_png_sha256'], t['outputs'][0]['png_sha256'])
                continue
            original = Path(t['outputs'][0]['png'])
            if not original.is_absolute(): original = ROOT/original
            src = np.array(Image.open(original).convert('RGBA'))
            dst = np.array(Image.open(record['gltf_png']).convert('RGBA'))
            self.assertTrue(np.array_equal(src[:, :, 3], dst[:, :, 3]))
            encoded = dst[:, :, :3]/255.0
            linear = np.where(encoded <= .04045, encoded/12.92, ((encoded+.055)/1.055)**2.4)
            self.assertLess(np.max(np.abs(linear-src[:, :, :3]/255)), .0045)

    def test_invalid_glb_chunk_bounds_rejected(self):
        for field in (8, 12):
            data = bytearray(self.glb)
            struct.pack_into('<I', data, field, 0x7fffffff)
            with self.assertRaises(ValueError): split_glb(data)
        with self.assertRaises(ValueError): split_glb(self.glb[:-1])


if __name__ == '__main__':
    unittest.main()
