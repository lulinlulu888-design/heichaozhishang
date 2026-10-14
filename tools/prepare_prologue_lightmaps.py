"""Recover scene lightmap payloads and per-instance bindings without guessing shading."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    raw = (ROOT / 'analysis/battle-visual/scene-00220.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '410761fae3aee0b8c67e9505831942d99eafb1dfa3380ea1a2e3699c963d53f7':
        raise ValueError('Scene identity mismatch')
    scene = ET.fromstring(raw)
    catalogue = read_catalogue(apk)
    out = ROOT / 'analysis/battle-visual/lightmaps'
    out.mkdir(exist_ok=True)
    table = scene.find('.//ModelLightmaps')
    base = table.find('LightMapPath').get('Path').replace('\\', '/')
    sources = []
    for entry in list(table)[1:]:
        logical = base + '/' + entry.get('Path')[:-4] + '.ktx'
        sources.append(extract(apk, catalogue, logical, out / (entry.tag + '.ktx'), APK_SHA256))
    provenance = out / 'sources.json'
    provenance.write_text(json.dumps(sources, indent=2), encoding='utf8')
    decoded = convert([Path(s['sample_path']) for s in sources], out / 'png', DEFAULT_DECODER,
                      provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    bindings, cache = [], {}
    for model in scene.iter('model'):
        lightmap = model.find('Lightmap')
        if lightmap is None:
            continue
        file_id = model.get('FilePathIndex')
        if file_id not in cache:
            payload = ROOT / f'analysis/battle-visual/scene-export/source/File_{file_id}.mesh'
            cache[file_id] = parse_model(payload.read_bytes())
        geometry = cache[file_id]
        if len(lightmap) != len(geometry['submeshes']):
            raise ValueError('Lightmap/submesh count mismatch')
        for index, (binding, submesh) in enumerate(zip(lightmap, geometry['submeshes'])):
            if not 0 <= int(binding.get('texture_index')) < len(sources):
                raise ValueError('Lightmap index outside source table')
            if len(submesh['uvs']) < 2:
                raise ValueError('Missing source UV1')
            bindings.append({'uuid': model.get('UUID'), 'name': model.get('Name'),
                             'file_id': file_id, 'submesh': index,
                             'uv1_count': len(submesh['uvs'][1]), 'parameters': binding.attrib})
    report = {'source_sha256': hashlib.sha256(raw).hexdigest(), 'sources': sources,
              'decoded_images': decoded['textures'], 'bindings': bindings,
              'scope': 'Linear encoded pixels and original UV1 bindings only; no final irradiance or lighting claim'}
    (out / 'bindings.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'textures': len(sources), 'submesh_bindings': len(bindings), 'uv1_verified': True}))


if __name__ == '__main__':
    main()
