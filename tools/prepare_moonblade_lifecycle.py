"""Recover original model lifetime and shader curves without running NeoX."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'


def main():
    report = json.loads((BASE / 'bindings.json').read_text('utf8'))
    src = next(r['source'] for r in report['files'] if r['source']['logical_path'] == 'effects/player/001/new_dazhao/yueren_zi.sfx')
    raw = Path(src['sample_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != src['sha256']: raise ValueError('Source effect changed')
    tree = ET.fromstring(raw.decode('gb18030'))
    parents = {child: parent for parent in tree.iter() for child in parent}
    models = []
    for model in tree.iter('Model'):
        logical = model.attrib['ModelName'].replace('\\', '/')
        if not logical.endswith('/plane_yueren.gim'): continue
        uniforms = model.find('./ShaderComponent/Uniforms')
        curves = {}
        for semantic in uniforms.findall('./Variables/Semantic'):
            curve = uniforms.find(semantic.attrib['Value'])
            curves[semantic.attrib['Name']] = {'type': semantic.attrib['Type'], 'attributes': curve.attrib,
                'frames': [{'time': float(f.attrib['Time']), 'value': [float(x) for x in f.attrib['Value'].split(',')]} for f in curve.findall('Frame')]}
        ancestors = []
        parent = parents.get(model)
        while parent is not None:
            ancestors.append({'tag': parent.tag, 'attributes': parent.attrib,
                              'tracks': [ET.tostring(t, encoding='unicode') for t in parent if t.tag.startswith('Track')]})
            parent = parents.get(parent)
        models.append({'source': logical, 'attributes': model.attrib, 'shaderCurves': curves, 'ancestors': ancestors})
    if len(models) != 1: raise ValueError('Ambiguous moonblade model')
    result = {'source': src, 'models': models, 'originalRuntimeExecuted': False,
              'previewTimePolicy': 'UE adaptation: linear interpolation over normalized model lifetime; native hierarchy/colour/interpolator semantics still unverified'}
    (BASE / 'moonblade-lifecycle.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'modelLifeSeconds': models[0]['attributes']['FxLifeSpan'], 'shaderCurves': list(models[0]['shaderCurves'])}))


if __name__ == '__main__': main()
