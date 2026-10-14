"""Export one source-identified prologue building as a textured GLB reference."""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract, split_glb, pack_glb
from export_neox_gltf import encode_glb
from extract_texture_samples import APK_SHA256
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/building'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Unexpected APK')
    catalogue = read_catalogue(apk)
    manifest = json.loads((ROOT / 'analysis/battle-visual/prologue-scene-manifest.json').read_text())
    entry, = [f for f in manifest['files'] if f['id'] == 'File_1']
    base = entry['path'][:-4].replace('\\', '/')
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {}
    for ext in ('gim', 'mesh', 'mtg'):
        sources[ext] = extract(apk, catalogue, base + '.' + ext, OUT / ('building.' + ext), APK_SHA256)
    model = parse_model((OUT / 'building.mesh').read_bytes())
    gim = ET.parse(OUT / 'building.gim').getroot()
    mtg = ET.parse(OUT / 'building.mtg').getroot()
    sub, = list(gim.find('SubMesh'))
    material, = list(mtg.find('MaterialGroup'))
    if int(sub.attrib['MtlIdx']) != 0 or len(model['submeshes']) != 1:
        raise ValueError('Expected one independently identified material slot')
    center = list(map(float, sub.attrib['BoundingCenter'].split(',')))
    half = list(map(float, sub.attrib['BoundingHalf'].split(',')))
    # This static scene GIM explicitly stores AABBs rounded to two decimals.
    errors = [abs(min(p[k] for p in model['positions']) - (center[k] - half[k])) for k in range(3)]
    errors += [abs(max(p[k] for p in model['positions']) - (center[k] + half[k])) for k in range(3)]
    if not all(math.isfinite(v) and v <= .011 for v in errors):
        raise ValueError('Geometry disagrees with rounded GIM bounds')
    tex = material.find('Material/ParamTable/Tex0').attrib['Value'].replace('\\', '/')
    texture_source = extract(apk, catalogue, tex.rsplit('.', 1)[0] + '.ktx', OUT / 'colour.ktx', APK_SHA256)
    provenance = OUT / 'texture-provenance.json'
    provenance.write_text(json.dumps([texture_source]), encoding='utf8')
    decoded = convert([OUT / 'colour.ktx'], OUT / 'png', DEFAULT_DECODER,
                      provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    png = Path(decoded['textures'][0]['outputs'][0]['png'])
    if not png.is_absolute():
        png = ROOT / png
    blob, _, _ = encode_glb(model, name=base)
    doc, binary = split_glb(blob)
    binary = bytearray(binary)
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    image = png.read_bytes()
    binary.extend(image)
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(image)})
    doc['images'] = [{'bufferView': len(doc['bufferViews']) - 1, 'mimeType': 'image/png'}]
    doc['textures'] = [{'source': 0}]
    doc['extensionsUsed'] = ['KHR_materials_unlit']
    doc['materials'] = [{'name': material.find('Material').attrib['Name'],
                         'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0, 'roughnessFactor': 1},
                         'extensions': {'KHR_materials_unlit': {}}, 'doubleSided': True}]
    for primitive in doc['meshes'][0]['primitives']:
        primitive['material'] = 0
    doc['extras']['missing'] = ['original lighting/lightmaps', 'normal and mix maps', 'source shader and culling semantics']
    doc['buffers'][0]['byteLength'] = len(binary)
    result = pack_glb(doc, binary)
    target = OUT / 'prologue-building.glb'
    target.write_bytes(result)
    report = {'source_path': entry['path'], 'sources': sources, 'texture_source': texture_source,
              'vertex_count': model['vertex_count'], 'triangle_count': model['triangle_count'],
              'gim_bounds_max_error': max(errors), 'glb_sha256': hashlib.sha256(result).hexdigest(),
              'glb_bytes': len(result), 'scope': 'Tex0 unlit reference; not original rendering or full scene',
              'source_instances': [m for m in manifest['models'] if m['FilePathIndex'] == '1']}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: report[k] for k in ('vertex_count', 'triangle_count', 'gim_bounds_max_error', 'glb_bytes')}))


if __name__ == '__main__':
    main()
