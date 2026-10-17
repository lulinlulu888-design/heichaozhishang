"""Index the two source effects named by boss skills 74501/74502/74503.

Extracts only those .sfx documents, checks the APK identity, and lists the
model/effect paths they name. It does not decode meshes, materials or particles
and does not import anything into Unreal.
"""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from decode_ktx import DEFAULT_DECODER, convert
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import lookup_logical, read_catalogue

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / 'analysis/prologue-boss/mechanism-audit/enemySkills.json'
SKILLS_SHA = '1be4dea9663cc97674efdc37e037f993d8cbc38d5d55e0aa6919339ebfe53d29'
OUT = ROOT / 'analysis/prologue-boss/skill-effects'
EXPECTED = {
    '74501': 'effects/boss/muoumaxitua/muoumaxituan_shouji_01.sfx',
    '74502': 'effects/boss/muoumaxitua/muoumaxituan_shouji_01.sfx',
    '74503': 'effects/boss/muoumaxitua/muoumaxituan_skill_2_03.sfx',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def summarize(payload):
    """Literal layer fields. TrackType, DirType and BlendMode are not interpreted."""
    root = ET.fromstring(payload.decode('gb18030'))
    layers = []
    for el in root.iter():
        if el.tag not in ('Sprite', 'ParticleSystem', 'Model'):
            continue
        layers.append({
            'tag': el.tag,
            'name': el.attrib.get('Name', ''),
            'texture': el.attrib.get('Texture', '').replace('\\', '/'),
            'start': el.attrib.get('FxStartTime', ''),
            'lifespan': el.attrib.get('FxLifeSpan', ''),
            'trackType': el.attrib.get('TrackType', ''),
            'dirType': el.attrib.get('DirType', ''),
            'blendMode': el.attrib.get('BlendMode', ''),
        })
    return root.tag, layers


def main():
    if sha(SKILLS.read_bytes()) != SKILLS_SHA:
        raise SystemExit('Boss skill evidence changed')
    rows = {str(row['id']): row['fields']['SKILL_TARGET_SFX'] for row in json.loads(SKILLS.read_text('utf8'))['rows']}
    if rows != EXPECTED:
        raise SystemExit('Boss skill effect paths changed')
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise SystemExit('APK identity mismatch')
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    documents = []
    for logical in sorted(set(EXPECTED.values())):
        target = OUT / 'source' / Path(logical).name
        source = extract(apk, catalogue, logical, target, APK_SHA256)
        payload = target.read_bytes()
        root_tag, layers = summarize(payload)
        textures = sorted({layer['texture'] for layer in layers if layer['texture']})
        documents.append({'logical': logical, 'sha256': sha(payload), 'bytes': len(payload), 'root': root_tag,
                          'layers': layers, 'textures': textures,
                          'source': {k: source[k] for k in ('member', 'index', 'logical_path') if k in source}})
    textures, texture_gaps = [], []
    for logical in sorted({layer['texture'] for doc in documents for layer in doc['layers'] if layer['texture']}):
        stem = Path(logical).stem
        candidates = [logical] if not logical.endswith('.tga') else [logical, str(Path(logical).with_suffix('.ktx'))]
        found = next((item for item in candidates if len(lookup_logical(catalogue, item)) == 1), None)
        if found is None:
            texture_gaps.append(logical)
            continue
        if found.endswith('.spr'):
            # The .spr names effect/texture/<stem>.tga, which is not in the pack.
            # The same-stem .ktx next to the .spr is; frames are cropped from it.
            sheet = str(Path(found).with_suffix('.ktx'))
            if len(lookup_logical(catalogue, sheet)) != 1:
                texture_gaps.append(logical)
                continue
            spr_path = OUT / 'textures' / (stem + '.spr')
            extract(apk, catalogue, found, spr_path, APK_SHA256)
            frames = []
            for line in spr_path.read_text('utf8', errors='replace').splitlines()[3:]:
                parts = line.split()
                if len(parts) != 5:
                    texture_gaps.append(logical)
                    frames = []
                    break
                frames.append([int(v) for v in parts[1:]])
            if not frames:
                continue
            sheet_path = OUT / 'textures' / (stem + '.ktx')
            extract(apk, catalogue, sheet, sheet_path, APK_SHA256)
            decoded = convert([sheet_path], OUT / 'textures' / ('decoded-' + stem), DEFAULT_DECODER)['textures'][0]['outputs'][0]
            with Image.open(ROOT / decoded['png']) as image:
                image = image.convert('RGBA')
                if any(x1 > image.width or y1 > image.height for _, _, x1, y1 in frames):
                    texture_gaps.append(logical)
                    continue
                crops = []
                for index, (x0, y0, x1, y1) in enumerate(frames):
                    crop = OUT / 'textures' / f'{stem}-{index}.png'
                    image.crop((x0, y0, x1, y1)).save(crop)
                    crops.append({'rect': [x0, y0, x1, y1], 'pngSha256': sha(crop.read_bytes())})
                textures.append({'logical': logical, 'packed': found, 'sheet': sheet, 'size': list(image.size),
                                 'frames': crops, 'pathNote': 'spr texture path is not indexed; frames come from the same-stem ktx'})
            continue
        target = OUT / 'textures' / (stem + Path(found).suffix)
        extract(apk, catalogue, found, target, APK_SHA256)
        if found.endswith('.ktx'):
            decoded = convert([target], OUT / 'textures' / ('decoded-' + stem), DEFAULT_DECODER)['textures'][0]['outputs'][0]
            png = ROOT / decoded['png']
        else:
            png = target.with_suffix('.png')
            with Image.open(target) as image:
                image.convert('RGBA').save(png)
        with Image.open(png) as image:
            textures.append({'logical': logical, 'packed': found, 'size': list(image.size), 'pngSha256': sha(png.read_bytes())})
    report = {'apkSha256': APK_SHA256, 'skills': EXPECTED, 'documents': documents, 'textures': textures,
              'textureGaps': texture_gaps,
              'limits': ['Layer fields are copied from the SFX. TrackType, DirType and BlendMode are not interpreted.',
                         'TGA textures are decoded to PNG. Particle motion is not reconstructed, and nothing is played.']}
    path = OUT / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'report': str(path), 'sha256': sha(path.read_bytes()),
                      'documents': [{'logical': d['logical'], 'layers': len(d['layers'])} for d in documents],
                      'textures': len(textures), 'textureGaps': texture_gaps},
                    ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
