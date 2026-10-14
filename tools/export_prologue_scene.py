"""Assemble original prologue meshes and Tex0 images; no original shader emulation."""
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
OUT = ROOT / 'analysis/battle-visual/scene-export'


def run():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Unexpected APK')
    cat = read_catalogue(apk)
    source = ROOT / 'analysis/battle-visual/scene-00220.bin'
    if hashlib.sha256(source.read_bytes()).hexdigest() != '410761fae3aee0b8c67e9505831942d99eafb1dfa3380ea1a2e3699c963d53f7':
        raise ValueError('Unexpected scene XML')
    xml = ET.fromstring(source.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {'asset': {'version': '2.0', 'generator': 'hczs prologue reference'},
           'bufferViews': [], 'accessors': [], 'meshes': [], 'nodes': [], 'images': [],
           'textures': [], 'materials': [], 'scenes': [{'nodes': []}], 'scene': 0,
           'extensionsUsed': ['KHR_materials_unlit']}
    binary = bytearray()
    texture_cache, meshes, sources, unresolved = {}, {}, [], []

    def get(logical, name):
        target = OUT / 'source' / name
        sources.append(extract(apk, cat, logical, target, APK_SHA256))
        return target

    def append_bytes(data):
        binary.extend(b'\0' * (-len(binary) % 4))
        offset = len(binary)
        binary.extend(data)
        return offset

    def texture(logical):
        logical = logical.replace('\\', '/')
        if logical in texture_cache:
            return texture_cache[logical]
        key = hashlib.sha256(logical.encode()).hexdigest()[:20]
        path = get(logical.rsplit('.', 1)[0] + '.ktx', key + '.ktx')
        result = convert([path], OUT / 'png' / key, DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
        png = Path(result['textures'][0]['outputs'][0]['png'])
        data = (png if png.is_absolute() else ROOT / png).read_bytes()
        offset = append_bytes(data)
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data)})
        doc['images'].append({'bufferView': len(doc['bufferViews']) - 1, 'mimeType': 'image/png'})
        doc['textures'].append({'source': len(doc['images']) - 1})
        texture_cache[logical] = len(doc['textures']) - 1
        return texture_cache[logical]

    for entry in xml.find('.//AllFiles'):
        logical = entry.attrib['Path'].replace('\\', '/')
        if not logical.endswith('.gim'):
            continue
        if logical == 'model/test/probe.gim':
            unresolved.append({'path': logical, 'reason': 'Absent from APK path index; not replaced'})
            continue
        key = entry.tag
        gim = ET.parse(get(logical, key + '.gim')).getroot()
        model = parse_model(get(logical[:-4] + '.mesh', key + '.mesh').read_bytes())
        mtg = ET.parse(get(logical[:-4] + '.mtg', key + '.mtg')).getroot()
        material_indices = []
        for material in mtg.find('MaterialGroup'):
            original = material.find('Material')
            tex0 = original.find('ParamTable/Tex0')
            if tex0 is None:
                raise ValueError(f'Missing Tex0: {logical}')
            texid = texture(tex0.attrib['Value'])
            material_indices.append(len(doc['materials']))
            doc['materials'].append({'name': original.attrib['Name'],
                'pbrMetallicRoughness': {'baseColorTexture': {'index': texid}, 'metallicFactor': 0, 'roughnessFactor': 1},
                'extensions': {'KHR_materials_unlit': {}}, 'doubleSided': True,
                'extras': {'sourceMaterialXML': ET.tostring(original, encoding='unicode'),
                           'scope': 'Opaque Tex0 colour reference; original render states retained, not interpreted'}})
            technique = original.find('Technique').get('TechName', '').replace('\\', '/')
            mode = original.find('RenderStates/TransparentMode').get('TransparentMode')
            if technique == 'shader/common_nolightuv.fx::TShader' and mode == '2':
                doc['materials'][-1]['alphaMode'] = 'BLEND'
                doc['materials'][-1]['extras']['scope'] = (
                    'Source sky shader returns texture alpha; conventional straight-alpha blending reference. '
                    'Native blend-state enum and HDR transfer are not yet reproduced.')
        blob, _, _ = encode_glb(model, logical)
        local, raw = split_glb(blob)
        offset = append_bytes(raw)
        view_base, acc_base = len(doc['bufferViews']), len(doc['accessors'])
        for view in local['bufferViews']:
            view['byteOffset'] = view.get('byteOffset', 0) + offset
            doc['bufferViews'].append(view)
        for accessor in local['accessors']:
            accessor['bufferView'] += view_base
            doc['accessors'].append(accessor)
        subs = list(gim.find('SubMesh'))
        primitives = local['meshes'][0]['primitives']
        if len(subs) != len(primitives):
            raise ValueError('GIM submesh count mismatch')
        for sub, primitive in zip(subs, primitives):
            primitive['indices'] += acc_base
            primitive['attributes'] = {k: v + acc_base for k, v in primitive['attributes'].items()}
            primitive['material'] = material_indices[int(sub.attrib['MtlIdx'])]
        meshes[entry.tag.replace('File_', '')] = len(doc['meshes'])
        doc['meshes'].append(local['meshes'][0])
    for instance in xml.iter('model'):
        data = instance.attrib
        key = data['FilePathIndex']
        if key not in meshes:
            continue
        matrix = list(map(float, data.get('Rotation', '1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1').split(',')))
        scale = list(map(float, data.get('Scale', '1,1,1').split(',')))
        position = list(map(float, data.get('Position', '0,0,0').split(',')))
        if len(matrix) != 16 or len(scale) != 3 or len(position) != 3:
            raise ValueError('Unexpected scene transform')
        for axis in range(3):
            for row in range(3):
                matrix[axis * 4 + row] *= scale[axis]
        matrix[12:15] = position
        if not all(math.isfinite(v) for v in matrix):
            raise ValueError('Nonfinite transform')
        doc['scenes'][0]['nodes'].append(len(doc['nodes']))
        doc['nodes'].append({'name': data['Name'], 'mesh': meshes[key], 'matrix': matrix,
                             'extras': {'sourceInstance': data}})
    doc['extras'] = {'sourceScene': 'scene/chess_xuzhang/chess_xuzhang.scn',
        'sourceCameras': [e.attrib for e in xml.iter('Camera')],
        'limitations': ['Transform convention requires visual verification; absent rotation/position/scale provisionally use identity/zero/one', 'No original lightmaps, lighting, effects, fog or sky',
                       'All source model flags retained, visibility semantics not yet interpreted', 'Sky alpha uses conventional BLEND; native blend-state mapping and HDR unverified; other alpha policies not reproduced'],
        'unresolved': unresolved}
    output = pack_glb(doc, binary)
    (OUT / 'prologue-scene.glb').write_bytes(output)
    report = {'apk_sha256': APK_SHA256, 'glb_sha256': hashlib.sha256(output).hexdigest(),
              'glb_bytes': len(output), 'meshes': len(doc['meshes']), 'instances': len(doc['nodes']),
              'textures': len(doc['textures']), 'materials': len(doc['materials']),
              'sources': sources, 'limitations': doc['extras']}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: report[k] for k in ('meshes', 'instances', 'textures', 'materials', 'glb_bytes')}))


if __name__ == '__main__':
    run()
