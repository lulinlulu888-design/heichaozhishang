import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import audit_boss_skill_effects as audit

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'analysis/prologue-boss/skill-effects/source'


class BossSkillEffectSummaryTest(unittest.TestCase):
    def test_hit_and_firework_layers_match_the_extracted_documents(self):
        hit_tag, hit = audit.summarize((SOURCE / 'muoumaxituan_shouji_01.sfx').read_bytes())
        fire_tag, fire = audit.summarize((SOURCE / 'muoumaxituan_skill_2_03.sfx').read_bytes())
        self.assertEqual((hit_tag, fire_tag), ('FxGroup', 'FxGroup'))
        self.assertEqual([layer['name'] for layer in hit],
                         ['L_旋转光环_an', 'L_baodian', 'M_baodianadd', 'H_ lizi', 'L_鬼火_1', 'M_旋转光环_刺光'])
        self.assertEqual([layer['lifespan'] for layer in hit], ['0.600', '0.120', '0.300', '0.500', '0.200', '0.200'])
        self.assertEqual(hit[0]['texture'], 'effects/tex/glow/glow_002.tga')
        self.assertEqual(len(fire), 10)
        self.assertEqual(fire[0]['name'], 'L_glow_add')
        self.assertTrue(all(layer['blendMode'] != '' and layer['trackType'] != '' for layer in hit + fire))
        report = json.loads((ROOT / 'analysis/prologue-boss/skill-effects/report.json').read_text('utf8'))
        glow = next(row for row in report['textures'] if row['logical'].endswith('glow_002.tga'))
        self.assertEqual(glow['size'], [128, 128])
        self.assertTrue(glow['packed'].replace('\\', '/').endswith('glow_002.ktx'))
        self.assertEqual(report['textureGaps'], ['effects/tex/star/suixie_xuelie01.spr'])


if __name__ == '__main__':
    unittest.main()
