"""The C++ entrance SFX table must only contain literals from the source recipe."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
RECIPE = ROOT / 'analysis/battle-visual/entrance-fx/playback-recipe.json'
SOURCE = ROOT / 'clients/unreal5 5.8/Source/Hczs/Private/HczsEntranceSourceFx.cpp'
MODELS = ('/FxGroup[1]/Dummy[1]/Dummy[1]/Model[1]', '/FxGroup[1]/Dummy[2]/Model[1]', '/FxGroup[1]/Dummy[3]/Model[1]')
CURVES = ('XScale', 'YScale', 'ZScale', 'ScaleFrame', 'alphaMtl_Keyframe', 'g_DissolveStrength_Keyframe',
          'g_fFloatingStrength1_Keyframe', 'g_colFloatingColor1_Keyframe')


def numbers(text):
    return sorted(round(float(v), 6) for v in re.findall(r'-?\d*\.?\d+(?=f?\b)', text))


@unittest.skipUnless(RECIPE.exists(), 'local source recipe not extracted')
class EntranceFxTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layers = {row['xpath']: row for row in json.loads(RECIPE.read_text('utf8'))['layers']}
        text = SOURCE.read_text('utf8')
        table = text[text.index('const TArray<FLayer>& Table()'):text.index('float Evaluate(')]
        starts = [table.index('TEXT("' + xpath + '")') for xpath in MODELS]
        cls.blocks = {xpath: table[start:(starts + [len(table)])[index + 1]] for index, (xpath, start) in enumerate(zip(MODELS, starts))}

    def expected(self, xpath):
        values = []
        chain = [xpath]
        while chain[-1].count('/') > 2:
            chain.append(chain[-1].rsplit('/', 1)[0])
        for path in chain[:-1] if chain[-1] == '/FxGroup[1]' else chain:
            row = self.layers[path]
            attributes = row['attributes']
            values += [float(attributes['FxStartTime']), float(attributes['FxLifeSpan'])]
            values += [float(v) for v in attributes['PosOffset'].split(',')]
            for curve in row.get('curves', []):
                if curve['tag'] not in CURVES or curve['xpath'].rsplit('/', 1)[0] not in (path, path + '/TrackScale[1]', path + '/ShaderComponent[1]/Uniforms[1]'):
                    continue
                for frame in curve['frames']:
                    # A single key is a constant, so its time carries no meaning.
                    times = [float(frame['Time'])] if len(curve['frames']) > 1 else []
                    values += times + [float(v) for v in frame['Value'].split(',')]
        return values

    def test_every_source_literal_is_in_the_layer_block(self):
        for xpath in MODELS:
            with self.subTest(layer=xpath):
                available = numbers(self.blocks[xpath])
                for value in self.expected(xpath):
                    rounded = round(value, 6)
                    if rounded in (0.0, 1.0):
                        continue
                    self.assertIn(rounded, available, f'{xpath} is missing source literal {value}')

    def test_model_names_match_source_gim(self):
        for xpath in MODELS:
            model = self.layers[xpath]['attributes']['ModelName'].replace('\\', '/').rsplit('/', 1)[-1][:-4]
            self.assertIn('TEXT("' + model + '")', self.blocks[xpath])


if __name__ == '__main__':
    unittest.main()
