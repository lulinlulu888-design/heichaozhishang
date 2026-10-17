"""Export the original map-50002 chess piece models as unlit Tex0 glTF files.

Pieces come from map_piece_setting ids used by map 50002 (1 start, 50 level
cells).  Every source material is common_nolight with TransparentMode 2, so the
glTF uses unlit straight-alpha blending; native blend enums stay unverified.
"""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract, split_glb, pack_glb
from export_neox_gltf import encode_glb
from extract_texture_samples import APK_SHA256
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/mainline-dungeon/pieces'
SETTINGS = ROOT / 'analysis/mainline-dungeon/data/map-piece-settings.json'
MAP = ROOT / 'analysis/mainline-dungeon/data/map50002.json'
FIELDS = ('PlayerPos', 'ExploreAble', 'ResUpper', 'Shadowed', 'Res', 'Explored')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(apk, cat, logical, sources):
    stem = Path(logical).stem
    work = OUT / 'source'
    work.mkdir(parents=True, exist_ok=True)

    def get(path, suffix):
        target = work / (stem + suffix)
        sources.append(extract(apk, cat, path, target, APK_SHA256))
        return target

    gim = ET.parse(get(logical, '.gim')).getroot()
    # Unlit source shader: normals are carried, never used for shading.
    model = parse_model(get(logical[:-4] + '.mesh', '.mesh').read_bytes(), preserve_nonunit_normals=True)
    mtg = ET.parse(get(logical[:-4] + '.mtg', '.mtg')).getroot()
    blob, _, _ = encode_glb(model, logical)
    doc, binary = split_glb(blob)
    binary = bytearray(binary)
    doc.update(images=[], textures=[], materials=[], samplers=[{'magFilter': 9729, 'minFilter': 9987}],
               extensionsUsed=['KHR_materials_unlit'])
    textures = {}
    materials = []
    for entry in mtg.find('MaterialGroup'):
        source = entry.find('Material')
        technique = source.find('Technique').get('TechName', '').replace('\\', '/')
        mode = source.find('RenderStates/TransparentMode').get('TransparentMode')
        if technique != 'shader/common_nolight.fx::TShader' or mode != '2':
            raise ValueError('Unexpected chess piece material: ' + logical)
        tex = source.find('ParamTable/Tex0').get('Value').replace('\\', '/')
        if tex not in textures:
            ktx = get(tex.rsplit('.', 1)[0] + '.ktx', '-' + hashlib.sha256(tex.encode()).hexdigest()[:12] + '.ktx')
            result = convert([ktx], OUT / 'png' / ktx.stem, DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
            png = Path(result['textures'][0]['outputs'][0]['png'])
            data = (png if png.is_absolute() else ROOT / png).read_bytes()
            binary.extend(b'\0' * (-len(binary) % 4))
            doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data)})
            binary.extend(data)
            doc['images'].append({'bufferView': len(doc['bufferViews']) - 1, 'mimeType': 'image/png'})
            doc['textures'].append({'source': len(doc['images']) - 1, 'sampler': 0})
            textures[tex] = len(doc['textures']) - 1
        materials.append(len(doc['materials']))
        doc['materials'].append({'name': stem + '_' + source.get('Name', ''),
            'pbrMetallicRoughness': {'baseColorTexture': {'index': textures[tex]}, 'metallicFactor': 0, 'roughnessFactor': 1},
            'alphaMode': 'BLEND', 'doubleSided': source.find('RenderStates').get('CullMode') == '0',
            'extensions': {'KHR_materials_unlit': {}},
            'extras': {'sourceMaterialXML': ET.tostring(source, encoding='unicode')}})
    subs = list(gim.find('SubMesh'))
    primitives = doc['meshes'][0]['primitives']
    if len(subs) != len(primitives):
        raise ValueError('GIM submesh count mismatch: ' + logical)
    for sub, primitive in zip(subs, primitives):
        primitive['material'] = materials[int(sub.attrib['MtlIdx'])]
    doc['buffers'] = [{'byteLength': len(binary)}]
    doc.setdefault('extras', {})['sourceModel'] = logical
    output = pack_glb(doc, bytes(binary))
    target = OUT / (stem + '.glb')
    target.write_bytes(output)
    return dict(logical=logical, glb=str(target.relative_to(ROOT)), sha256=hashlib.sha256(output).hexdigest(),
                materials=len(doc['materials']), textures=sorted(textures))


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('Unexpected APK')
    settings = {row['id']: row['fields'] for row in json.loads(SETTINGS.read_text('utf8'))['rows']}
    game_map = json.loads(MAP.read_text('utf8'))['data']
    used = {1, game_map['Global']['normalMPieceId']}
    cat = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    sources, models = [], {}
    for piece in sorted(used):
        for field in FIELDS:
            logical = settings[piece].get(field)
            if logical and logical not in models:
                models[logical] = export(apk, cat, logical, sources)
    report = dict(apkSha256=APK_SHA256, settingsSha256=digest(SETTINGS), mapSha256=digest(MAP),
        pieces={str(p): {f: settings[p].get(f) for f in FIELDS + ('ResUpper_Pos', 'ResUpper_Scale', 'ResUpper_Rotate', 'Res_Scale')}
                for p in sorted(used)},
        models=models, sources=sources,
        limitations=['common_nolight TransparentMode 2 exported as unlit straight-alpha BLEND; native blend enum unverified',
                     'ResUpper float/rotate animation (ResUpper_Vec/Duration) and ResUpper_Sfx are not exported'])
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({k: v['sha256'][:12] for k, v in models.items()}))


if __name__ == '__main__':
    main()
