"""Recover source FightPanel frames with the verified png-to-pkm loader mapping."""
import hashlib
import json
import plistlib
import re
import shutil
from pathlib import Path
from PIL import Image
from inspect_neox_model import extract_npk_entry
from decode_ktx import convert, DEFAULT_DECODER
from extract_texture_samples import APK_SHA256
from export_elsa_model import extract
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'
FRAMES = {
    'energy-bg': 'energy_bg.png', 'end-bg': 'end_bg.png',
    'energy-icon': 'energy_icon_s2.png',
    'end-icon-normal': 'end_icon_s1.png', 'end-icon-active': 'end_icon_s2.png',
    'player-hp': 'bloodbar/img_hp_normal.png', 'player-hp-bg': 'bloodbar/img_hp_bg.png',
    'enemy-hp': 'bloodbar/img_boss_hp_low_normal.png', 'enemy-hp-bg': 'bloodbar/img_boss_hp_bg.png',
    'monster-hp': 'bloodbar/img_hp_low.png', 'monster-hp-bg': 'bloodbar/img_hp_bg.png',
    'shield-icon': 'bloodbar/img_shield_s_s1.png',
    'head-back': 'bloodbar/img_hparea_headbg1.png',
    'head-front': 'bloodbar/img_hparea_headbg2.png',
    'deck-icon': 'icon/btn_deck.png',
}


def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    plist_path = OUT/'FightPanel.plist'
    catalogue = read_catalogue(apk)
    plist_source = extract(apk, catalogue, 'uires/FightPanel.plist', plist_path, APK_SHA256)
    texture_path = OUT/'atlas-4589.ktx'
    texture_source = extract(apk, catalogue, 'uires/FightPanel.pkm', texture_path, APK_SHA256)
    if plist_source['sha256'] != 'dced510b8dee2c8451b01475aeed05e756fa6d29c6044c456f160721f2303359' or texture_source['sha256'] != '1c1a54ff26bf934c9da8e8a558cd72ba8265ca2d74bec265ecf0d2cbaa7fa61c':
        raise ValueError('Pinned atlas sources changed')
    decoded = convert([texture_path], OUT/'decoded-4589', DEFAULT_DECODER)
    image_record = decoded['textures'][0]['outputs'][0]
    atlas = Image.open(ROOT/image_record['png']).convert('RGBA')
    if atlas.size != (4096, 4096):
        raise ValueError('Unexpected atlas size')
    plist = plistlib.loads(plist_path.read_bytes())
    rows = []
    dest = ROOT/'legacy/cocos-poc/assets/resources/recovered/battle-ui'
    dest.mkdir(parents=True, exist_ok=True)
    for name, suffix in FRAMES.items():
        key = 'FightPanel/FightNewPanel/res/'+suffix
        frame = plist['frames'][key]
        x, y, w, h = map(int, re.findall(r'-?\d+', frame['frame']))
        sx, sy, sw, sh = map(int, re.findall(r'-?\d+', frame['sourceColorRect']))
        source_size = tuple(map(int, re.findall(r'\d+', frame['sourceSize'])))
        rotated = frame['rotated']
        rw, rh = (h, w) if rotated else (w, h)
        if not (0 <= x < x+rw <= atlas.width and 0 <= y < y+rh <= atlas.height):
            raise ValueError('Frame outside atlas')
        sprite = atlas.crop((x, y, x+rw, y+rh))
        if rotated:
            sprite = sprite.transpose(Image.Transpose.ROTATE_90)
        if sprite.size != (sw, sh) or not (0 <= sx <= sx+sw <= source_size[0] and 0 <= sy <= sy+sh <= source_size[1]):
            raise ValueError('Trim dimensions inconsistent')
        canvas = Image.new('RGBA', source_size)
        canvas.paste(sprite, (sx, sy))
        output = OUT/(name+'.png')
        canvas.save(output)
        shutil.copyfile(output, dest/(name+'.png'))
        rows.append(dict(name=name, logical_frame=key, frame=frame, png=str(output.relative_to(ROOT)),
            png_sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
    report = dict(apk_sha256=APK_SHA256, plist_source=plist_source, texture_source=texture_source,
        decoded=image_record, frames=rows,
        attribution='Exact logical plist and texture paths with verified png-to-pkm loader suffix mapping; pinned hashes also match earlier coordinate attribution.',
        scope='Original sprite pixels, reconstructed placement; no original CSB animation or layout execution.')
    (OUT/'sprites.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    shutil.copyfile(OUT/'sprites.json', dest/'provenance.json')
    print(json.dumps(dict(sprites=len(rows), destination=str(dest))))


if __name__ == '__main__':
    main()
