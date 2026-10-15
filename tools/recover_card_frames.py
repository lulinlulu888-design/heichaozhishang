"""Recover original small-card frames through source VT mappings; never execute APK code."""
import hashlib
import json
import plistlib
import re
import struct
import shutil
from pathlib import Path
from PIL import Image
from decode_ktx import IDENTIFIER, convert, DEFAULT_DECODER
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_card_virtual_textures import parse_table
from neox_resource_paths import read_catalogue, parse_vt_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui/card-frames'


def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    OUT.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    sources = {}
    for name in ('vt.table', 'vt_config.jsondata'):
        sources[name] = extract(apk, catalogue, 'packed_png/vt_data/'+name, OUT/name, APK_SHA256)
    sources['cost_normal.fnt'] = extract(apk, catalogue, 'uires/CommonRes/Fnt/cost_normal.fnt', OUT/'cost_normal.fnt', APK_SHA256)
    table = parse_table((OUT/'vt.table').read_bytes())
    config = parse_vt_config((OUT/'vt_config.jsondata').read_bytes())
    names = {n['key']:n['name'] for n in table['names']}
    pages = {r[1]:r for r in table['records']}
    mappings = {r['key']:r for r in config['pngsToPageID']}
    frames = {}
    atlas_sources = {6039:'4b6a3e565077be87898956b8f745a908d64102df27348570c28cb82c23a1b829',
        10583:'6478b44ef7ba724749931187f0a0d73d0870c426d17d46243e918e0b199cdf6a',
        9638:'65471d0b7f2c6bdece546f8a6b9b92045a65d2e4c55a50b674df919de71c6afb',
        908:'8d0e8f7a3f54985d1c033f21fdc34a626941c9e8b9f166b24c0f608a41494dc4',
        8734:'baf4fbfc60eb977b70e0d6acbd6bca630e55435bd16eb1b23e85c7edcdaab5a5'}
    for number, digest in atlas_sources.items():
        plist_path = ROOT/f'analysis/battle-ui/card-atlas-{number}.plist'
        if hashlib.sha256(plist_path.read_bytes()).hexdigest() != digest:
            raise ValueError('Card atlas source changed')
        frames.update(plistlib.loads(plist_path.read_bytes())['frames'])
    rows = []
    for kind in ('atk', 'skill', 'def', 'cost', 'cost_normal', 'big-atk'):
        key = 'card/bg_atk.png' if kind == 'big-atk' else 'cost_normal.png' if kind == 'cost_normal' else 'card/cost_s1.png' if kind == 'cost' else f'card/bg_{kind}_s.png'
        mapping = mappings[key]
        x,y,w,h = mapping['value']
        if not (0 < w <= 8 and 0 < h <= 8):
            raise ValueError('Unexpected tile rectangle')
        canvas = Image.new('RGBA',(w*124,h*124))
        tiles = []
        for dy in range(h):
            for dx in range(w):
                address = (y+dy)*512+x+dx
                level, _, offset, name_key = pages[address]
                if level != 0:
                    raise ValueError('Unexpected layer')
                raw = OUT/f'{address}.bin'
                source = extract(apk,catalogue,f'packed_png/vt_data/astc/{names[name_key]}/{offset}',raw,APK_SHA256)
                payload = raw.read_bytes()
                if len(payload) != 16384:
                    raise ValueError('Unexpected tile size')
                ktx = raw.with_suffix('.ktx')
                ktx.write_bytes(IDENTIFIER+struct.pack('<13I',0x04030201,0,1,0,0x93B0,0x1908,128,128,0,0,1,1,0)+struct.pack('<I',len(payload))+payload)
                decoded = convert([ktx],OUT/f'decoded-{address}',DEFAULT_DECODER)
                image = decoded['textures'][0]['outputs'][0]
                with Image.open(ROOT/image['png']) as tile:
                    canvas.paste(tile.convert('RGBA').crop((2,2,126,126)),(dx*124,dy*124))
                tiles.append(dict(address=address,source=source,decoded=image))
        frame = frames[key]
        fx,fy,fw,fh = map(int,re.findall(r'-?\d+',frame['frame']))
        sx,sy,sw,sh = map(int,re.findall(r'-?\d+',frame['sourceColorRect']))
        size = tuple(map(int,re.findall(r'\d+',frame['sourceSize'])))
        rw,rh = (fh,fw) if frame['rotated'] else (fw,fh)
        left,top = fx-x*124,fy-y*124
        if not (0 <= left < left+rw <= canvas.width and 0 <= top < top+rh <= canvas.height):
            raise ValueError('Frame outside mapped tiles')
        sprite = canvas.crop((left,top,left+rw,top+rh))
        if frame['rotated']:
            sprite = sprite.transpose(Image.Transpose.ROTATE_90)
        if sprite.size != (sw,sh) or not (0 <= sx <= sx+sw <= size[0] and 0 <= sy <= sy+sh <= size[1]):
            raise ValueError('Invalid source trim')
        restored = Image.new('RGBA',size)
        restored.paste(sprite,(sx,sy))
        path = OUT/f'{kind}.png'
        restored.save(path)
        rows.append(dict(key=key,mapping=mapping,frame=frame,tiles=tiles,png=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    report = dict(apk_sha256=APK_SHA256,sources=sources,atlas_sources=atlas_sources,frames=rows,
        assumptions=['ASTC 4x4 LDR linear decode', 'Row-major VT width 512, 124px stride, two-pixel border', 'Original runtime colour profile unverified'],
        scope='Original image candidates and source metadata; no runtime card-layout fidelity claim')
    (OUT/'provenance.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    cards = json.loads((ROOT/'analysis/first-encounter/player-cards.json').read_text('utf8'))['rows']
    if {r['id'] for r in cards} != {110001,110009,210003,410101,410102} or any(r['fields']['CARD_TYPE'] != 0 for r in cards):
        raise ValueError('Preview card types need explicit frame mapping')
    dest = ROOT/'legacy/cocos-poc/assets/resources/recovered/card-frames'
    dest.mkdir(parents=True,exist_ok=True)
    for name in ('atk.png','skill.png','def.png','cost.png','cost_normal.png','cost_normal.fnt','big-atk.png','provenance.json'):
        shutil.copyfile(OUT/name,dest/name)
    # Creator 3.8.8 retains the signed BMFont size and uses it as a scale divisor.
    # Keep the original file in analysis; normalize only the shared-client derivative.
    font_text = (OUT/'cost_normal.fnt').read_text('utf8')
    if font_text.count('size=-32') != 1:
        raise ValueError('Unexpected source font size')
    (dest/'cost_normal.fnt').write_text(font_text.replace('size=-32','size=32'),encoding='utf8')
    report['client_font_adaptation'] = dict(change='size=-32 to size=32 for Creator positive glyph scale',
        sha256=hashlib.sha256((dest/'cost_normal.fnt').read_bytes()).hexdigest(), source_unchanged=True)
    for path in (OUT/'provenance.json',dest/'provenance.json'):
        path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps([dict(key=r['key'],png=r['png']) for r in rows]))


if __name__ == '__main__':
    main()
