"""Crop the battle auto and speed icons from the pinned FightPanel atlas."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'analysis/battle-ui/decoded-4589/atlas-4589.1c1a54ff26bf.m0.f0.png'
OUT = ROOT / 'analysis/battle-ui/auto-speed-icons'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
atlas = Image.open(ATLAS).convert('RGBA')
if atlas.size != (4096, 4096):
    raise SystemExit(f'unexpected atlas {atlas.size}')
OUT.mkdir(parents=True, exist_ok=True)
frames = []
auto = Image.new('RGBA', (56, 56))
auto.paste(atlas.crop((317, 2589, 317 + 56, 2589 + 52)), (0, 0))
auto_png = OUT / 'auto-icon.png'
auto.save(auto_png)
frames.append({
    'name': 'auto-icon',
    'logical': 'FightPanel/FightNewPanel/res/icon/btn_auto.png',
    'png': 'analysis/battle-ui/auto-speed-icons/auto-icon.png',
    'png_sha256': hashlib.sha256(auto_png.read_bytes()).hexdigest(),
    'size': [56, 56],
    'rotated': False,
    'atlas_frame': '{{317,2589},{56,52}}',
    'source_color_rect': '{{0,0},{56,52}}',
})
speed = atlas.crop((593, 2580, 593 + 56, 2580 + 56))
speed_png = OUT / 'speed-icon.png'
speed.save(speed_png)
frames.append({
    'name': 'speed-icon',
    'logical': 'FightPanel/FightNewPanel/res/icon/btn_speed.png',
    'png': 'analysis/battle-ui/auto-speed-icons/speed-icon.png',
    'png_sha256': hashlib.sha256(speed_png.read_bytes()).hexdigest(),
    'size': [56, 56],
    'rotated': False,
    'atlas_frame': '{{593,2580},{56,56}}',
})
report = {'apk_sha256': APK, 'frames': frames}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest())
