"""Compare actual UE GPU center samples against pinned decoded source mip PNGs."""
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/reflection/boss_theatre'
OUT = ROOT / 'analysis/unreal/battle-reference/reflection-gpu-comparison.json'


def center_rgb(image):
    """Independent bilinear sample at the exact center of a face."""
    w, h = image.size
    xs = [max(0, (w-1)//2), min(w-1, w//2)]
    ys = [max(0, (h-1)//2), min(h-1, h//2)]
    return [sum(image.getpixel((x,y))[c] for y in ys for x in xs) / (4*255)
            for c in range(3)]


def compare(samples, expected, tolerance=0.0015):
    keys = [(s['face'],s['mip']) for s in samples]
    if len(keys) != len(set(keys)) or set(keys) != set(expected):
        raise ValueError('Actual sample set is missing, duplicated or unexpected')
    rows = []
    for sample in samples:
        key = sample['face'], sample['mip']
        rgb = sample['rgb']
        if len(rgb) != 3 or not all(isinstance(v, (int,float)) and math.isfinite(v) for v in rgb):
            raise ValueError('GPU sample is not three finite numeric channels')
        error = max(abs(a-b) for a,b in zip(rgb, expected[key]))
        rows.append(dict(face=key[0], mip=key[1], expectedRGB=expected[key], actualRGB=rgb, maximumError=error))
    maximum = max(row['maximumError'] for row in rows)
    return dict(passed=maximum <= tolerance, tolerance=tolerance, maximumError=maximum, samples=rows)


def main():
    dds = json.loads((BASE / 'dds.json').read_text('utf8'))
    sampled_file = ROOT / 'analysis/unreal/battle-reference/reflection-gpu-sampling.json'
    sampled_bytes = sampled_file.read_bytes()
    sampled = json.loads(sampled_bytes)
    if sampled['sourceDdsSha256'] != dds['ddsSha256'] or len(dds['decodedInputs']) != 48:
        raise ValueError('Source cube identity or complete face/mip matrix differs')
    expected = {}
    for row in dds['decodedInputs']:
        path = Path(row['png']).resolve()
        if not path.is_relative_to(BASE.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Pinned decoded face PNG changed')
        with Image.open(path) as image:
            expected[row['face'],row['mip']] = center_rgb(image.convert('RGBA'))
    result = compare(sampled['samples'], expected)
    result.update(sourceDdsSha256=dds['ddsSha256'], nativeReadbackSha256=hashlib.sha256(sampled_bytes).hexdigest(),
        scope='GPU face-center bilinear RGB parity at 48 authored face/mip locations only; not all pixels or original engine/cube orientation equivalence.')
    OUT.write_text(json.dumps(result, indent=2), 'utf8')
    print(json.dumps({k:result[k] for k in ('passed','maximumError','tolerance')}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
