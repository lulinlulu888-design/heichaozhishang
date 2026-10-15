"""Convert original ultimate geometry, retaining source material slots separately."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from export_elsa_model import bind_materials, parse_materials, split_glb, pack_glb
from export_neox_gltf import encode_glb
from inspect_neox_model import parse_model, ModelError
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'


def main():
    report = json.loads((BASE / 'bindings.json').read_text('utf8'))
    if report['apkSha256'] != APK_SHA256:
        raise ValueError('Wrong source APK')
    sources = {f['source']['logical_path']: f['source'] for f in report['files']}

    def read(logical):
        source = sources[logical]
        raw = Path(source['sample_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256'] or source['apk_sha256'] != APK_SHA256:
            raise ValueError('Recovered resource changed: ' + logical)
        return raw

    output = BASE / 'glb'
    output.mkdir(exist_ok=True)
    models, unresolved = [], []
    for logical in sorted(sources):
        if not logical.endswith('.gim'):
            continue
        gim = read(logical)
        tree = ET.fromstring(gim.decode('gb18030'))
        mesh_path = tree.attrib.get('Mesh', logical[:-4] + '.mesh').replace('\\', '/')
        mtg_path = logical[:-4] + '.mtg'
        model = parse_model(read(mesh_path))
        materials = parse_materials(read(mtg_path), expected_slots=None)
        try:
            bindings = bind_materials(model, gim, materials)
        except ModelError as error:
            unresolved.append({'gim': logical, 'mesh': mesh_path, 'reason': str(error)})
            continue
        name = Path(logical).stem
        blob, _, _ = encode_glb(model, name, skin=False)
        doc, binary = split_glb(blob)
        # Slot placeholders identify original materials; shader implementation is separate.
        doc['materials'] = [{'name': f'{name}_slot_{i}', 'extras': {'originalMaterial': m, 'shaderImplemented': False}}
                            for i, m in enumerate(materials)]
        for primitive, binding in zip(doc['meshes'][0]['primitives'], bindings):
            primitive['material'] = binding['material_slot']
        doc['extras']['sourceGim'] = logical
        doc['extras']['sourceMesh'] = mesh_path
        blob = pack_glb(doc, binary)
        target = output / (name + '-' + hashlib.sha256(logical.encode()).hexdigest()[:8] + '.glb')
        target.write_bytes(blob)
        models.append({'gim': logical, 'mesh': mesh_path, 'materialGroup': mtg_path,
                       'explicitMeshReference': 'Mesh' in tree.attrib, 'bindings': bindings,
                       'materials': materials, 'glb': str(target), 'sha256': hashlib.sha256(blob).hexdigest(),
                       'vertices': len(model['positions']), 'submeshes': len(model['submeshes'])})
    result = {'apkSha256': APK_SHA256, 'models': models, 'unresolved': unresolved, 'shadersImplemented': False,
              'coordinatePolicy': 'Original XYZ/scale/UV/winding retained; apply established UE coordinate adapter at import.'}
    (BASE / 'mesh-export.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'models': len(models), 'explicitMeshReuse': sum(m['explicitMeshReference'] for m in models),
                      'materialSlots': sum(len(m['materials']) for m in models), 'unresolved': unresolved}))


if __name__ == '__main__':
    main()
