"""Real enemy geometry/material/skin checks plus corrupt-evidence rejection."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from export_tutorial_enemy import (HASHES, audit_glb, identity_chain, parse_material,
                                   shader_evidence, validate_reference_bind)
from export_elsa_model import bind_materials, pack_glb, split_glb
from inspect_neox_model import ModelError, parse_model, validate_bind_pose
from inspect_neox_animation import parse_library

OUT = ROOT/'analysis/tutorial-enemy'


@unittest.skipUnless((OUT/'export-report.json').is_file(), 'real enemy export must be generated first')
class TutorialEnemyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((OUT/'export-report.json').read_text('utf8'))
        cls.gim = (OUT/'source/enemy-991.gim').read_bytes()
        cls.mtg = (OUT/'source/enemy-991.mtg').read_bytes()
        cls.model = parse_model((OUT/'source/enemy-991.mesh').read_bytes())
        cls.library = parse_library((OUT/'source/enemy-991.gisacl').read_bytes())
        cls.material = parse_material(cls.mtg)
        cls.blob = (OUT/'tutorial-enemy-991.colour-reference.glb').read_bytes()
        cls.doc, cls.binary = split_glb(cls.blob)

    def test_source_identity_chain_and_archive_hashes(self):
        chain = identity_chain()
        self.assertEqual([r['id'] for r in chain['rows']], [991, 6605, 6605, 66051])
        self.assertEqual(chain['name'], '幻眼魔方')
        self.assertEqual(chain['entity_scale_unapplied'], [.7, .7, .7])
        for suffix, expected in HASHES.items():
            blob = (OUT/'source'/f'enemy-991.{suffix}').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), expected)
        self.assertEqual([self.report['sources'][s]['index'] for s in ('gim', 'mesh', 'mtg', 'gisacl')],
                         [6648, 1902, 6425, 6081])

    def test_real_full_geometry_and_skin_roundtrip(self):
        model = self.model
        self.assertEqual((model['vertex_count'], model['triangle_count'], len(model['bones']), model['submesh_count']),
                         (4208, 6246, 61, 1))
        self.assertEqual(model['coverage_bytes'], 314503)
        self.assertEqual(len(model['submeshes'][0]['uvs']), 1)
        audit = audit_glb(self.blob, model)
        self.assertEqual(audit, self.report['glb_readback_validation'])
        self.assertLess(audit['max_cpu_bind_position_error'], 1e-5)
        self.assertLess(audit['max_inverse_times_global_identity_error'], 1e-5)
        self.assertEqual(audit['max_inverse_bind_storage_error'], 0)
        self.assertEqual(hashlib.sha256(self.blob).hexdigest(), self.report['glb_sha256'])
        self.assertEqual(len(self.blob), self.report['glb_bytes'])

    def test_auxiliary_not_reinterpreted_or_silently_relaxed(self):
        with self.assertRaisesRegex(ModelError, 'independent bind-pose bounds check failed'):
            validate_bind_pose(self.model)
        bind = validate_reference_bind(self.model, self.library)
        self.assertFalse(bind['auxiliary_aabb_check']['validated'])
        self.assertEqual(len(bind['rows']), 61)
        self.assertLess(bind['max_global_error'], 3e-6)
        self.assertLess(bind['max_local_error'], 1e-6)
        saved = json.loads((OUT/'bone-map.json').read_text('utf8'))
        for source, row in zip(self.model['bones'], saved['bones']):
            self.assertEqual(list(source['auxiliary_unknown']), row['source_auxiliary_unknown'])

    def test_library_name_order_does_not_determine_bone_mapping(self):
        altered = copy.deepcopy(self.library)
        altered['bone_names'].reverse()
        altered['reference_pose'].reverse()
        self.assertEqual(validate_reference_bind(self.model, altered)['rows'],
                         validate_reference_bind(self.model, self.library)['rows'])
        altered['bone_names'][0] = altered['bone_names'][1]
        with self.assertRaisesRegex(ModelError, 'same 61 unique bone names'):
            validate_reference_bind(self.model, altered)

    def test_changed_reference_pose_rejected(self):
        altered = copy.deepcopy(self.library)
        altered['reference_pose'][0] = list(altered['reference_pose'][0])
        altered['reference_pose'][0][0] += .01
        with self.assertRaisesRegex(ModelError, 'reference bind differs'):
            validate_reference_bind(self.model, altered)

    def test_material_slot_geometry_and_effect_scope(self):
        rows = bind_materials(self.model, self.gim, [self.material])
        self.assertEqual(rows[0]['material_slot'], 0)
        self.assertLess(rows[0]['bounds_max_error'], 1e-4)
        self.assertEqual(self.material['technique']['Surface'], 'shader/surface/emission.surf')
        self.assertEqual(self.material['macros'], {'EXT_EMISSIVE': 'TRUE', 'EMISSIVE_TEXTURE': 'TRUE'})
        doc = self.doc
        self.assertEqual(len(doc['materials']), 1)
        self.assertEqual(len(doc['images']), 1)
        material = doc['materials'][0]
        self.assertEqual(material['extensions'], {'KHR_materials_unlit': {}})
        self.assertEqual(material['alphaMode'], 'OPAQUE')
        self.assertNotIn('emissiveTexture', material)
        self.assertNotIn('normalTexture', material)
        self.assertNotIn('occlusionTexture', material)
        self.assertEqual(material['pbrMetallicRoughness']['baseColorTexture'], {'index': 0, 'texCoord': 0})
        self.assertEqual([t['parameter'] for t in self.report['texture_inventory'] if t['exported_as_colour']], ['Tex0'])

    def test_invalid_material_and_submesh_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            parse_material(self.mtg.replace(b'MaterialCount="1"', b'MaterialCount="2"'))
        with self.assertRaisesRegex(ValueError, 'unsupported material technique'):
            parse_material(self.mtg.replace(b'emission.surf', b'basic.surf'))
        with self.assertRaisesRegex(ModelError, 'material slot'):
            bind_materials(self.model, self.gim.replace(b'MtlIdx = "0"', b'MtlIdx = "1"'), [self.material])
        with self.assertRaisesRegex(ModelError, 'bounds mismatch'):
            bind_materials(self.model, self.gim.replace(b'0.237300', b'1.237300'), [self.material])

    def test_shader_actual_uv_colour_and_emission_evidence(self):
        evidence = shader_evidence(OUT/'shader-evidence')
        self.assertEqual(evidence, self.report['shader_semantics'])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for p in (OUT/'shader-evidence').iterdir():
                if p.suffix in ('.hlsl', '.surf'): (directory/p.name).write_bytes(p.read_bytes())
            p = directory/'material_emission.hlsl'
            p.write_text(p.read_text('utf8').replace('raw_data.tex0.rgb * BaseColor.rgb;', 'raw_data.tex2.rgb * BaseColor.rgb;'), 'utf8')
            with self.assertRaisesRegex(ValueError, 'shader evidence'):
                shader_evidence(directory)

    def test_embedded_colour_png_and_all_mip_block_validation(self):
        from PIL import Image
        import io
        image = self.doc['images'][0]
        view = self.doc['bufferViews'][image['bufferView']]
        png = self.binary[view['byteOffset']:view['byteOffset']+view['byteLength']]
        record = self.report['decoded_colour_texture']
        self.assertEqual(hashlib.sha256(png).hexdigest(), record['gltf_png_sha256'])
        decoded = record['decoder_record']
        self.assertEqual(decoded['block_validation']['validated_mips'], decoded['texture']['mip_count'])
        self.assertEqual(decoded['block_validation']['error_blocks'], 0)
        self.assertEqual(decoded['block_validation']['hdr_blocks'], 0)
        self.assertEqual(decoded['texture']['profile'], 'srgb')
        with Image.open(io.BytesIO(png)) as pixels:
            self.assertEqual(pixels.convert('RGBA').getextrema()[3], (255, 255))
            self.assertEqual(pixels.size, (decoded['texture']['width'], decoded['texture']['height']))

    def test_changed_parent_inverse_bind_and_vertex_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc['nodes'][62]['children'].append(1)
        with self.assertRaisesRegex(ValueError, 'multiple node parents'):
            audit_glb(pack_glb(doc, self.binary), self.model)
        for accessor, message in [(self.doc['skins'][0]['inverseBindMatrices'], 'inverse/global bind mismatch'),
                                  (self.doc['meshes'][0]['primitives'][0]['attributes']['POSITION'], 'source array changed')]:
            binary = bytearray(self.binary)
            view = self.doc['bufferViews'][self.doc['accessors'][accessor]['bufferView']]
            position = view['byteOffset']
            struct.pack_into('<f', binary, position, struct.unpack_from('<f', binary, position)[0]+.125)
            with self.assertRaisesRegex(ValueError, message):
                audit_glb(pack_glb(copy.deepcopy(self.doc), binary), self.model)


if __name__ == '__main__':
    unittest.main()
