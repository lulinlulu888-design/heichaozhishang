"""Crop NameLabelArea and its Power_water mark sprites from pinned decoded atlases."""
import hashlib
import json
import plistlib
import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/card-owner'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
ATLASES = {
    'CommonUI': ('analysis/battle-ui/entrance/sprites/CommonUI/atlas.plist',
                 'analysis/battle-ui/entrance/sprites/CommonUI/decoded/atlas.15fd120cf08c.m0.f0.png'),
    'FightPanel': ('analysis/battle-ui/entrance/sprites/FightPanel/atlas.plist',
                   'analysis/battle-ui/entrance/sprites/FightPanel/decoded/atlas.1c1a54ff26bf.m0.f0.png'),
}
# NameLabelArea_ext.csb bg, and CardOtherControls.NameLabelArea._typeAreas indexed by CharPos
# (RIGHT 0, MID 1, LEFT 2): Power_water_yellow/Purple/BlueArea, each a Water_drop_*_00 sprite.
FRAMES = [
    ('card-owner-bg', 'CommonUI', 'Common/Res/FightNewRes/smallcard_bg_black.png'),
    ('card-owner-mark-0', 'FightPanel', 'FightPanel/FightNewPanel/res/Water_drop_VX/Water_drop_Yellow_00.png'),
    ('card-owner-mark-1', 'FightPanel', 'FightPanel/FightNewPanel/res/Water_drop_VX/Water_drop_Purple_00.png'),
    ('card-owner-mark-2', 'FightPanel', 'FightPanel/FightNewPanel/res/Water_drop_VX/Water_drop_Blue_00.png'),
]


def numbers(text):
    return [int(v) for v in re.findall(r'-?\d+', text)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    loaded, sources = {}, {}
    for name, (plist_path, png_path) in ATLASES.items():
        plist_bytes = (ROOT / plist_path).read_bytes()
        data = plistlib.loads(plist_bytes)
        atlas = Image.open(ROOT / png_path).convert('RGBA')
        if atlas.size != tuple(numbers(data['metadata']['size'])):
            raise ValueError(f'{name} atlas size differs from its plist')
        loaded[name] = (data['frames'], atlas)
        sources[name] = {'plist': plist_path, 'plist_sha256': hashlib.sha256(plist_bytes).hexdigest(),
                         'png': png_path, 'png_sha256': hashlib.sha256((ROOT / png_path).read_bytes()).hexdigest()}
    rows = []
    for key, atlas_name, logical in FRAMES:
        frames, atlas = loaded[atlas_name]
        frame = frames[logical]
        fx, fy, fw, fh = numbers(frame['frame'])
        sx, sy, sw, sh = numbers(frame['sourceColorRect'])
        size = numbers(frame['sourceSize'])
        crop = atlas.crop((fx, fy, fx + (fh if frame['rotated'] else fw), fy + (fw if frame['rotated'] else fh)))
        if frame['rotated']:
            crop = crop.transpose(Image.Transpose.ROTATE_90)
        if crop.size != (sw, sh):
            raise ValueError(f'{logical} trim rectangle mismatch')
        image = Image.new('RGBA', tuple(size))
        image.paste(crop, (sx, sy))
        png = OUT / f'{key}.png'
        image.save(png)
        rows.append({'name': key, 'logical': logical, 'atlas': atlas_name, 'frame': frame,
                     'png': png.relative_to(ROOT).as_posix(),
                     'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(), 'size': size})
    report = {'apk_sha256': APK, 'atlases': sources, 'frames': rows,
              'layout': {'csb': 'uires/FightPanel/FightNewPanel/NameLabelArea_ext.csb',
                         'bg': {'anchor': [1, 1], 'position': [0, 0], 'size': [32, 100]},
                         'mark': {'position': [-16, -17], 'scale': 0.75, 'panelScale': 0.59},
                         'txt': {'anchor': [0.5, 1], 'position': [-17, -36], 'size': [19, 46],
                                 'fontSize': 22, 'font': 'CommonRes/title.ttf'},
                         'root': 'card local (-getCardWidth/2 - 4, getCardHeight/2 + 3 + CTRL1.y), card rotation'}}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
