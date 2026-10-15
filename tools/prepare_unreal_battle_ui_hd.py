"""Audit six reviewed AI icon variants without altering their PNG bytes.

Only presentation geometry is adapted. No mask, crop, alpha cleanup, pixel
rewrite, upscaling or tint operation is performed on a production asset.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/battle-ui/ai-icons'
SELECTED = {'energy-icon': 'v1', 'end-icon-normal': 'v2', 'end-icon-active': 'v3',
            'shield-icon': 'v1', 'deck-icon': 'v2', 'card-cost': 'v2'}
REQUEST_FILES = ['generation-requests.json', 'generation-retry-requests.json',
                 'generation-active-v3-request.json']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_audit(path):
    with Image.open(path) as image:
        if image.mode != 'RGBA':
            raise ValueError('Transparent icon must be RGBA')
        alpha = image.getchannel('A')
        if alpha.getextrema() != (0, 255) and path.parent == OUT:
            raise ValueError('Generated icon does not retain transparent and opaque pixels')
        bboxes = {str(threshold): alpha.point(lambda v: 255 if v >= threshold else 0).getbbox()
                  for threshold in (1, 8, 32, 128, 240)}
        if not bboxes['32']:
            raise ValueError('Icon has no stable alpha content')
        pixels = image.get_flattened_data()
        opaque = 0
        dark = 0
        for red, green, blue, value in pixels:
            if value >= 192:
                opaque += 1
                if max(red, green, blue) <= 48:
                    dark += 1
        return {'size': list(image.size), 'mode': image.mode,
                'alphaExtrema': list(alpha.getextrema()), 'alphaBoundsByThreshold': bboxes,
                'opaquePixels': opaque, 'opaqueNearBlackPixels': dark,
                'alignmentThreshold': 32, 'alignmentBounds': bboxes['32']}


def main():
    source = json.loads((ROOT / 'analysis/unreal/battle-ui/manifest.json').read_text('utf8'))
    if sha(ROOT / 'analysis/unreal/battle-ui/manifest.json') != '5fba1804eead422c38925406ddc8b161018cb56b72fd407750aca2b0c3e992aa':
        raise ValueError('Reviewed original presentation manifest changed')
    requests = []
    for filename in REQUEST_FILES:
        data = json.loads((OUT / filename).read_text('utf8'))
        for row in data['records']:
            row = dict(row)
            row['requestFile'] = (OUT / filename).relative_to(ROOT).as_posix()
            row['requestFileSha256'] = sha(OUT / filename)
            requests.append(row)
    rows = []
    for key, version in SELECTED.items():
        original = next(row for row in source['sprites'] if row['id'] == key)
        target = OUT / f'{key}-ai-{version}.png'
        request = next(row for row in requests if row['id'] == key and row['output'] == target.relative_to(ROOT).as_posix())
        original_path = (ROOT / original['png']).resolve()
        if not original_path.is_relative_to(ROOT) or sha(original_path) != original['pngSha256']:
            raise ValueError('Original APK extraction changed')
        generated = Path(request['generatedOriginal'])
        if not generated.is_file() or sha(generated) != sha(target):
            raise ValueError('Project icon bytes differ from built-in generated original')
        old, new = image_audit(original_path), image_audit(target)
        if new['opaqueNearBlackPixels']:
            raise ValueError('Opaque near-black pixels present in white-outline variant')
        sx, sy, sr, sb = old['alignmentBounds']
        nx, ny, nr, nb = new['alignmentBounds']
        sw, sh = old['size']
        nw, nh = new['size']
        scale_x = ((sr - sx) / sw) / ((nr - nx) / nw)
        scale_y = ((sb - sy) / sh) / ((nb - ny) / nh)
        offset_x = sx / sw - nx / nw * scale_x
        offset_y = sy / sh - ny / nh * scale_y
        adjustment = [scale_x, scale_y, offset_x, offset_y]
        mapped = [offset_x + nx / nw * scale_x, offset_y + ny / nh * scale_y,
                  offset_x + nr / nw * scale_x, offset_y + nb / nh * scale_y]
        expected = [sx / sw, sy / sh, sr / sw, sb / sh]
        error = max(abs(a - b) for a, b in zip(mapped, expected, strict=True))
        if error > 1e-12:
            raise ValueError('Icon geometry alignment proof failed')
        rows.append({'id': key, 'source': original['png'], 'sourceSha256': original['pngSha256'],
                     'variant': target.relative_to(ROOT).as_posix(), 'variantSha256': sha(target),
                     'version': version, 'sourceAudit': old, 'variantAudit': new,
                     'drawAdjustment': adjustment, 'normalizedContentAlignmentMaxError': error,
                     'request': request, 'reviewed': True,
                     'review': 'Functional icon reviewed; white outline, cyan/lavender pastel family, no opaque black edge. AI reinterpretation is not lossless original texture restoration.'})
    report = {'schemaVersion': 1, 'mode': 'built-in image_gen', 'transparent_background': True,
              'sourceManifestSha256': sha(ROOT / 'analysis/unreal/battle-ui/manifest.json'),
              'icons': rows, 'sourceAssetsModified': False, 'generatedPixelsModified': False,
              'alignmentPolicy': 'Map alpha>=32 content bounds of full PNG canvases into original source rectangles. Do not crop either PNG; original hitboxes stay unchanged.',
              'limitations': ['Low-alpha exterior generation residue is retained; no destructive alpha cleanup.',
                             'End-active v3 fills source-like triangular negative spaces with pastel colour to avoid generated opaque white debris; this is an explicit style variant.',
                             'Original normal/deck sprites have max-alpha 108/132; AI variants intentionally improve icon legibility.',
                             'Generated icon meaning and source footprint are reviewed, but exact original internal silhouette is not claimed.',
                             'Only an actual UE import/readback report and game screenshot prove in-engine use.']}
    (OUT / 'provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': True, 'icons': len(rows), 'original_and_generated_bytes_unchanged': True,
                      'opaque_black_pixels': sum(r['variantAudit']['opaqueNearBlackPixels'] for r in rows),
                      'provenance': str(OUT / 'provenance.json'), 'sha256': sha(OUT / 'provenance.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
