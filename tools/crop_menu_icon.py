"""Crop btn_menu_s2 from the pinned FightPanel atlas into a 56x56 source canvas."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'analysis/battle-ui/decoded-4589/atlas-4589.1c1a54ff26bf.m0.f0.png'
OUT = ROOT / 'analysis/battle-ui/menu-icon'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
atlas = Image.open(ATLAS).convert('RGBA')
if atlas.size != (4096, 4096):
    raise SystemExit(f'unexpected atlas {atlas.size}')
sprite = atlas.crop((281, 3338, 281 + 52, 3338 + 52))
canvas = Image.new('RGBA', (56, 56))
canvas.paste(sprite, (1, 0))
OUT.mkdir(parents=True, exist_ok=True)
png = OUT / 'menu-icon.png'
canvas.save(png)
digest = hashlib.sha256(png.read_bytes()).hexdigest()
report = {
    'apk_sha256': APK,
    'logical': 'FightPanel/FightNewPanel/res/icon/btn_menu_s2.png',
    'png': 'analysis/battle-ui/menu-icon/menu-icon.png',
    'png_sha256': digest,
    'size': [56, 56],
    'rotated': False,
    'atlas_frame': '{{281,3338},{52,52}}',
    'source_color_rect': '{{1,0},{52,52}}',
}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
report_sha = hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest()
print(json.dumps({'png_sha256': digest, 'report_sha256': report_sha}))
