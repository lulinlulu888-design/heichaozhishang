"""Recover the socket SFX sprites that draw map-50002 chess cell rings.

The piece meshes zq_suozai/zq_xuanzhong/zq_yizouguo carry a fully transparent
Tex0; their visible hexagon rings are Socket_1 SFX sprites (MatrixToBone 1.75).
Only flat DirType=2 sprites are converted.  Colour keys are ARGB.  The native
BlendMode enum and ColorFrame ChangeType interpolation remain unverified.
"""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/mainline-dungeon/cell-fx'
PIECES = ROOT / 'analysis/mainline-dungeon/pieces/report.json'
MODELS = ('zq_suozai', 'zq_xuanzhong', 'zq_yizouguo')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def floats(text):
    return [float(v) for v in text.split(',')]


def keys(node, tag):
    frame = node.find(tag)
    if frame is None:
        return []
    return [dict(time=float(f.get('Time')), value=floats(f.get('Value'))) for f in frame.findall('Frame')]


def sprites(node, rotation=0.0, path=()):
    for child in node:
        if child.tag == 'Dummy':
            angle = 0.0
            rotate = child.find('TrackRotate')
            if rotate is not None:
                if rotate.get('StartAngle') != rotate.get('EndAngle') or floats(rotate.get('AxesDir')) != [0, 1, 0]:
                    raise ValueError('Animated or tilted dummy rotation is not converted')
                angle = float(rotate.get('StartAngle'))
            yield from sprites(child, rotation + angle, path + (child.get('Name'),))
        elif child.tag == 'Sprite':
            if child.get('DirType') != '2' or floats(child.get('Direction')) != [0, 1, 0]:
                raise ValueError('Only flat upward sprites are converted')
            scale = child.find('TrackScale')
            yield dict(name='/'.join(path + (child.get('Name'),)), texture=child.get('Texture').replace('\\', '/'),
                radius=float(child.get('Radius')), posOffset=floats(child.get('PosOffset')),
                lifeSpan=float(child.get('FxLifeSpan')), blendMode=int(child.get('BlendMode')),
                renderBias=int(child.get('RenderBias', '0')), yawDegrees=rotation,
                colorChangeType=int(child.find('ColorFrame').get('ChangeType')),
                colorKeysArgb=keys(child, 'ColorFrame'),
                scaleKeys=keys(scale, 'XScale') if scale is not None else [],
                scaleTimeLen=float(scale.get('TimeLen')) if scale is not None else 0.0)
        elif child.tag == 'Model':
            yield dict(name='/'.join(path + (child.get('Name'),)), unconverted='model-effect-with-custom-shader',
                       model=child.get('ModelName').replace('\\', '/'))
        elif child.tag not in ('TrackFixPoint', 'TrackRotate'):
            raise ValueError('Unconverted SFX element: ' + child.tag)


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('Unexpected APK')
    cat = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    sources, effects, textures = [], {}, {}
    for model in MODELS:
        gim_path = OUT / 'source' / (model + '.gim')
        gim_path.parent.mkdir(parents=True, exist_ok=True)
        sources.append(extract(apk, cat, 'model/chess_3d/' + model + '.gim', gim_path, APK_SHA256))
        socket = ET.fromstring(gim_path.read_bytes()).find('Sockets')[0]
        matrix = floats(socket.get('MatrixToBone'))
        if matrix != [1.75, 0, 0, 0, 0, 1.75, 0, 0, 0, 0, 1.75, 0, 0, 0, 0, 1]:
            raise ValueError('Unexpected socket transform: ' + model)
        logical = socket.find('BoundObject/Object').get('Name').replace('\\', '/')
        sfx_path = OUT / 'source' / (model + '.sfx')
        sources.append(extract(apk, cat, logical, sfx_path, APK_SHA256))
        raw = sfx_path.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('gb18030')  # Undeclared authoring-tool encoding for Chinese layer names.
        rows = list(sprites(ET.fromstring(text)))
        skipped = [row for row in rows if 'unconverted' in row]
        rows = [row for row in rows if 'unconverted' not in row]
        for row in rows:
            tex = row['texture']
            if tex not in textures:
                ktx = OUT / 'source' / (Path(tex).stem + '.ktx')
                sources.append(extract(apk, cat, tex.rsplit('.', 1)[0] + '.ktx', ktx, APK_SHA256))
                result = convert([ktx], OUT / 'png' / ktx.stem, DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
                png = Path(result['textures'][0]['outputs'][0]['png'])
                png = png if png.is_absolute() else ROOT / png
                textures[tex] = dict(png=str(png.relative_to(ROOT)), sha256=digest(png))
        effects[model] = dict(sfx=logical, socketScale=1.75, sprites=rows, unconverted=skipped)
    report = dict(apkSha256=APK_SHA256, piecesReportSha256=digest(PIECES), effects=effects, textures=textures,
        sources=sources,
        limitations=['Colour keys are ARGB on normalised sprite life; linear interpolation is assumed for ChangeType values',
                     'BlendMode 0 is treated as straight alpha and other values as additive; native enum unverified',
                     'TrackScale pulses and SmoothStart/Stop fades are retained in data, not rendered'])
    target = OUT / 'recipe.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({k: len(v['sprites']) for k, v in effects.items()}), digest(target))


if __name__ == '__main__':
    main()
