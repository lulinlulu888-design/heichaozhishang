"""Crop the head shield track from the pinned FightPanel atlas."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'analysis/battle-ui/decoded-4589/atlas-4589.1c1a54ff26bf.m0.f0.png'
OUT = ROOT / 'analysis/battle-ui/shield-bars'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
FRAMES = {
    'shield-bg': ((1955, 2105, 156, 16), 'FightPanel/FightNewPanel/res/bloodbar/img_shield_bg.png'),
    'shield-fill': ((1955, 2123, 156, 16), 'FightPanel/FightNewPanel/res/bloodbar/img_shield.png'),
}
atlas = Image.open(ATLAS).convert('RGBA')
if atlas.size != (4096, 4096):
    raise SystemExit(f'unexpected atlas {atlas.size}')
OUT.mkdir(parents=True, exist_ok=True)
frames = []
for name, ((x, y, w, h), logical) in FRAMES.items():
    sprite = atlas.crop((x, y, x + w, y + h))
    png = OUT / f'{name}.png'
    sprite.save(png)
    frames.append({
        'name': name,
        'logical': logical,
        'png': f'analysis/battle-ui/shield-bars/{name}.png',
        'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(),
        'size': [w, h],
        'rotated': False,
        'atlas_frame': f'{{{{{x},{y}}},{{{w},{h}}}}}',
    })
report = {'apk_sha256': APK, 'frames': frames}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(json.dumps({
    'frames': [(row['name'], row['png_sha256']) for row in frames],
    'report_sha256': hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest(),
}))
