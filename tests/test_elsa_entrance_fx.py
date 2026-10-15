"""Source-backed entrance conversion checks; no engine or target execution."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_elsa_entrance_fx import (PINS, SFX, MODEL_PREFIX, APPROVED, EXCLUDED,
    make_recipe, pinned, prepare_material_inputs, shader_parameters, verify_geometry)
from export_elsa_model import bind_materials, pack_glb, parse_materials, split_glb
from inspect_neox_model import parse_model, ModelError

OUT = ROOT/'analysis/battle-visual/entrance-fx'


@unittest.skipUnless((OUT/'export-report.json').is_file(), 'run entrance offline preparation first')
class EntranceFxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((OUT/'export-report.json').read_text('utf8'))
        cls.recipe = json.loads((OUT/'playback-recipe.json').read_text('utf8'))
        cls.materials = json.loads((OUT/'material-inputs.json').read_text('utf8'))
        cls.textures = json.loads((OUT/'texture-manifest.json').read_text('utf8'))
        cls.sources = json.loads((OUT/'sourcepins.json').read_text('utf8'))

    def test_all_pinned_original_payloads_verified(self):
        self.assertEqual(len(PINS), 25)
        self.assertEqual(self.sources['pins'], PINS)
        for logical, expected in PINS.items():
            blob = (OUT/'source'/logical).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), expected)
            source = self.sources['sources'][logical]
            self.assertEqual(source['sha256'], expected)
            self.assertEqual(source['logical_path'], logical)
            self.assertIn(source['member'], ['assets/res/effects.npk', 'assets/res/shader.npk'])

    def test_complete_sfx_tree_and_hierarchical_model_curves(self):
        parsed = make_recipe((OUT/'source'/SFX).read_bytes())
        self.assertEqual(parsed['xmlTree'], self.recipe['xmlTree'])
        self.assertEqual(parsed['layers'], self.recipe['layers'])
        self.assertEqual(parsed['layerCounts'], {'Dummy': 6, 'FxCamera': 1, 'Model': 4, 'ParticleSystem': 2, 'Sprite': 6})
        models = [l for l in parsed['layers'] if l['tag'] == 'Model']
        self.assertEqual([len(l['ancestors']) for l in models], [3, 2, 2, 2])
        first = models[0]
        self.assertEqual(first['attributes']['FxStartTime'], '0.050')
        self.assertEqual(first['attributes']['FxLifeSpan'], '0.700')
        self.assertEqual(first['ancestors'][1]['attributes']['PosOffset'], '0.000000,0.000000,-10.000000')
        self.assertEqual(first['ancestors'][2]['attributes']['PosOffset'], '0.000000,-0.954676,0.000000')
        strength = next(c for c in models[2]['curves'] if c['tag'] == 'g_fFloatingStrength1_Keyframe')
        self.assertEqual([(f['Time'],f['Value']) for f in strength['frames']], [('0.5','5')])
        self.assertEqual(models[1]['trackNodes'][0]['attributes']['Forward'], '0.000,0.000,1.000,0.000')
        # No descendant layer's curves may be incorrectly owned by its parent.
        parent = next(l for l in parsed['layers'] if l['xpath'] == '/FxGroup[1]/Dummy[1]')
        self.assertEqual([c['tag'] for c in parent['curves']], ['XScale', 'YScale', 'ZScale'])

    def test_three_original_geometry_arrays_byte_exact(self):
        self.assertEqual([r['name'] for r in self.report['models']], list(APPROVED))
        self.assertEqual([(r['vertices'],r['triangles']) for r in self.report['models']], [(82,80),(72,70),(72,70)])
        for row in self.report['models']:
            raw = (OUT/'source'/row['mesh']).read_bytes()
            model = parse_model(raw)
            blob = Path(row['glb']).read_bytes()
            self.assertEqual(verify_geometry(blob, raw, model), row['verification'])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), row['sha256'])
            self.assertEqual(model['coverage_bytes'], len(raw))
            self.assertLess(row['bindings'][0]['bounds_max_error'], 1e-4)
            doc, _ = split_glb(blob)
            self.assertEqual(doc['materials'][0]['extras']['originalMaterial'], row['materials'][0])
            self.assertFalse(doc['materials'][0]['extras']['shaderImplemented'])

    def test_energy_column_stays_rejected_by_unchanged_gate(self):
        excluded, = self.report['excludedModels']
        self.assertEqual(excluded['name'], EXCLUDED)
        self.assertFalse(excluded['geometryExported'])
        self.assertFalse((OUT/(EXCLUDED+'.glb')).exists())
        prefix = MODEL_PREFIX+EXCLUDED
        model = parse_model((OUT/'source'/(prefix+'.mesh')).read_bytes())
        materials = parse_materials((OUT/'source'/(prefix+'.mtg')).read_bytes(), expected_slots=1)
        with self.assertRaisesRegex(ModelError, 'independent bounds mismatch'):
            bind_materials(model, (OUT/'source'/(prefix+'.gim')).read_bytes(), materials)

    def test_all_ten_pngs_linear_unchanged_and_every_mip_checked(self):
        from PIL import Image
        self.assertEqual(len(self.textures['textures']), 10)
        blocks = 0
        for texture in self.textures['textures']:
            self.assertEqual(texture['texture']['profile'], 'linear')
            checks = texture['block_validation']
            self.assertEqual(checks['validated_mips'], texture['texture']['mip_count'])
            self.assertEqual((checks['error_blocks'], checks['hdr_blocks']), (0,0))
            blocks += checks['block_count']
            image = texture['outputs'][0]
            path = ROOT/image['png']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), image['png_sha256'])
            with Image.open(path) as img:
                self.assertEqual(hashlib.sha256(img.convert('RGBA').tobytes()).hexdigest(), image['rgba_sha256'])
                self.assertEqual(img.size, (texture['texture']['width'], texture['texture']['height']))
        self.assertEqual(blocks, 11632)

    def test_materials_port_only_actual_macro_and_dynamic_inputs(self):
        rows = self.materials['materials']
        self.assertEqual([r['name'] for r in rows], list(APPROVED))
        self.assertEqual([[t['input'] for t in r['textures']] for r in rows], [['Color','Dissolve'],['Color','Noise'],['Color','Noise']])
        self.assertEqual([r['dynamicDefaults']['SourceAlpha'] for r in rows], [1,1,2])
        self.assertEqual([r['dynamicDefaults']['SourceStrength'] for r in rows], [1,1,5])
        for row in rows:
            self.assertEqual((OUT/(row['name']+'.hlsl')).read_text('utf8'), row['code']+'\n')
            self.assertTrue(all(t['srgb'] is False for t in row['textures']))
            self.assertIn('(c.rgb * c.rgb) * (SourceTint * SourceTint)', row['code'])
            self.assertNotIn('c.r * c.r', row['code'])
            self.assertFalse(any(t['input'] in ('Mask','Flow2') for t in row['textures']))
        self.assertIn('float noise = 0.0', rows[0]['code'])
        self.assertIn('pow(saturate((dissolve - SourceDissolve + 0.1) * 5.0), 0.5)', rows[0]['code'])
        self.assertIn('float2(0.2,0)', rows[1]['code'])
        self.assertIn('float2(3,1)', rows[2]['code'])

    def test_changed_source_unhandled_macro_and_missing_alpha_rejected(self):
        raw = (OUT/'source'/SFX).read_bytes()
        with self.assertRaisesRegex(ValueError, 'unreviewed or changed'):
            make_recipe(raw+b' ')
        with self.assertRaisesRegex(ValueError, 'unreviewed or changed'):
            pinned('unreviewed.sfx', raw)
        changed = copy.deepcopy(self.recipe['models'])
        changed[0]['materials'][0]['macros']['TWO_FLOAT'] = 'TRUE'
        with self.assertRaisesRegex(ValueError, 'unsupported entrance material macro'):
            prepare_material_inputs(changed, self.recipe, self.recipe['shader'], self.textures)
        changed_recipe = copy.deepcopy(self.recipe)
        for l in changed_recipe['layers']:
            if l['tag']=='Model':l['curves']=[c for c in l['curves'] if c['tag']!='alphaMtl_Keyframe']
        with self.assertRaisesRegex(ValueError, 'no explicit alphaMtl'):
            prepare_material_inputs(self.recipe['models'], changed_recipe, self.recipe['shader'], self.textures)

    def test_geometry_mutation_and_shader_mutation_rejected(self):
        row = self.report['models'][0]
        source = (OUT/'source'/row['mesh']).read_bytes()
        model = parse_model(source)
        doc, binary = split_glb(Path(row['glb']).read_bytes())
        accessor = doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
        offset = doc['bufferViews'][accessor['bufferView']]['byteOffset']
        struct.pack_into('<f', binary, offset, 123.0)
        with self.assertRaisesRegex(ValueError, 'differs from original bytes'):
            verify_geometry(pack_glb(doc, binary), source, model)
        shader = (OUT/'source/shader/lancer3.fx').read_bytes()
        helper = (OUT/'source/shader/shaderlib/function.fxl').read_bytes()
        with self.assertRaisesRegex(ValueError, 'unreviewed or changed'):
            shader_parameters(shader.replace(b'local_17.rgb', b'local_17.rrr'), helper)


if __name__ == '__main__':
    unittest.main()
