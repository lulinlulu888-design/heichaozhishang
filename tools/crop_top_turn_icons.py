"""Crop the no-damage remaining-turn plate from the pinned FightPanel atlas."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'analysis/battle-ui/decoded-4589/atlas-4589.1c1a54ff26bf.m0.f0.png'
OUT = ROOT / 'analysis/battle-ui/top-turn'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
atlas = Image.open(ATLAS).convert('RGBA')
if atlas.size != (4096, 4096):
    raise SystemExit(f'unexpected atlas {atlas.size}')
OUT.mkdir(parents=True, exist_ok=True)
frames = []
bg = atlas.crop((2550, 2524, 2550 + 192, 2524 + 34))
bg_png = OUT / 'top-info-bg.png'
bg.save(bg_png)
frames.append({
    'name': 'top-info-bg',
    'logical': 'FightPanel/FightNewPanel/res/TopInfo_bg1.png',
    'png': 'analysis/battle-ui/top-turn/top-info-bg.png',
    'png_sha256': hashlib.sha256(bg_png.read_bytes()).hexdigest(),
    'size': [192, 34],
    'rotated': False,
    'atlas_frame': '{{2550,2524},{192,34}}',
    'source_color_rect': '{{0,0},{192,34}}',
})
icon = Image.new('RGBA', (20, 18))
icon.paste(atlas.crop((4079, 273, 4079 + 14, 273 + 18)), (3, 0))
icon_png = OUT / 'top-info-icon.png'
icon.save(icon_png)
frames.append({
    'name': 'top-info-icon',
    'logical': 'FightPanel/FightNewPanel/res/TopInfo_icon1.png',
    'png': 'analysis/battle-ui/top-turn/top-info-icon.png',
    'png_sha256': hashlib.sha256(icon_png.read_bytes()).hexdigest(),
    'size': [20, 18],
    'rotated': False,
    'atlas_frame': '{{4079,273},{14,18}}',
    'source_color_rect': '{{3,0},{14,18}}',
    'source_size': [20, 18],
})
report = {'apk_sha256': APK, 'frames': frames}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest())
