"""Crop the battle chat and record icons from the pinned FightPanel atlas."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'analysis/battle-ui/decoded-4589/atlas-4589.1c1a54ff26bf.m0.f0.png'
OUT = ROOT / 'analysis/battle-ui/side-icons'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
FRAMES = (
    ('chat-icon', 'FightPanel/FightNewPanel/res/icon/btn_1_fight_chat_s1.png', (923, 2354, 56, 56)),
    ('record-icon', 'FightPanel/FightNewPanel/res/icon/btn_history.png', (631, 2857, 56, 56)),
)
atlas = Image.open(ATLAS).convert('RGBA')
if atlas.size != (4096, 4096):
    raise SystemExit(f'unexpected atlas {atlas.size}')
OUT.mkdir(parents=True, exist_ok=True)
frames = []
for name, logical, (x, y, width, height) in FRAMES:
    image = atlas.crop((x, y, x + width, y + height))
    png = OUT / (name + '.png')
    image.save(png)
    frames.append({
        'name': name,
        'logical': logical,
        'png': 'analysis/battle-ui/side-icons/' + name + '.png',
        'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(),
        'size': [width, height],
        'rotated': False,
        'atlas_frame': '{{%d,%d},{%d,%d}}' % (x, y, width, height),
    })
report = {'apk_sha256': APK, 'frames': frames}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest())
