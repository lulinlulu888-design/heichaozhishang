"""Recover source-linked VT portraits or buff 66051's icon without execution."""
import hashlib
import argparse
import json
import plistlib
import re
import shutil
import struct
import zipfile
from pathlib import Path
from PIL import Image
from decode_ktx import IDENTIFIER, convert, DEFAULT_DECODER
from export_elsa_model import extract
from extract_npk import decode_entry
from extract_texture_samples import APK_SHA256
from inspect_card_virtual_textures import parse_table
from neox_resource_paths import read_catalogue, parse_vt_config
from extract_game_data import export_table
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]


def main(actor='monster', entity=None):
    if actor == 'breakdown':
        table_index, entity_id, field, stem, asset = 391, 66051, 'BUFF_ICON', 'buff-66051', 'breakdown-icon'
    elif actor == 'player':
        table_index, entity_id, field, stem, asset = 8185, entity or 1, 'BattleIcon', f'player-{entity or 1}', 'player-head'
    else:
        table_index, entity_id, field, stem, asset = 2363, entity or 991, 'MonsterHead', f'monster-{entity or 991}', 'monster-head'
    # The first-encounter pair keeps its original directories; other IDs get their own.
    OUT = ROOT / (f'analysis/battle-ui/health/{actor}-portrait' if entity in (None, 1, 991)
                  else f'analysis/battle-ui/health/{stem}-portrait')
    table = literal_table(table_index, {entity_id}) if actor == 'breakdown' else export_table(table_index, [entity_id])
    logical = table['rows'][0]['fields'][field]
    report = recover_virtual_sprite(logical, OUT, stem, provenance=dict(
        actor=actor, source_table=table, source_field=field))
    if entity in (None, 1, 991):
        destination = ROOT/f'legacy/cocos-poc/assets/resources/recovered/battle-ui/{asset}.png'
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/report['output'], destination)
    print(json.dumps(dict(output=report['output'], size=report['size'], tiles=len(report['tiles']),
                          scanned=report['scanned_metadata_candidates'])))


def recover_virtual_sprite(logical, output_directory, stem='sprite', provenance=None):
    """Shared source-path -> VT alias -> unique atlas frame -> original pixels.

    Does not write client assets. All decoded output stays under analysis, and
    callers retain the static table/script binding separately from VT assumptions.
    """
    OUT = Path(output_directory).resolve()
    if not OUT.is_relative_to((ROOT/'analysis').resolve()) or Path(stem).name != stem:
        raise ValueError('VT output must stay in analysis with a plain filename')
    if not isinstance(logical, str) or not logical.startswith('uires/') or not logical.endswith('.png'):
        raise ValueError('Expected explicit original UI PNG path')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    sources = {}
    for name in ('vt.table', 'vt_config.jsondata'):
        sources[name] = extract(apk, catalogue, 'packed_png/vt_data/' + name, OUT/name, APK_SHA256)
    config = parse_vt_config((OUT/'vt_config.jsondata').read_bytes())
    matches = [r for r in config['fullPathToPng'] if r['key'].lower() == logical.lower()]
    if len(matches) != 1:
        raise ValueError('Ambiguous VT alias')
    alias = matches[0]
    mapping = [r for r in config['pngsToPageID'] if r['key'] == alias['value']]
    if len(mapping) != 1:
        raise ValueError('Ambiguous VT rectangle')
    frame_matches = []
    pack = next(p for p in catalogue if p['member'] == 'assets/res/packed_png.npk')
    scanned = 0
    with zipfile.ZipFile(apk) as archive, archive.open(pack['member']) as stream:
        for row in sorted(pack['entries'], key=lambda r: r['offset']):
            if row['original_size'] == 16384 or row['original_size'] > 4*1024*1024:
                continue
            stream.seek(row['offset'])
            payload = decode_entry(stream.read(row['stored_size']), {**row, 'offset': 0}, max_decoded_bytes=4*1024*1024)
            scanned += 1
            if not payload.lstrip().startswith((b'<?xml', b'<plist')) or b'<plist' not in payload[:300]:
                continue
            data = plistlib.loads(payload)
            if alias['value'] in data.get('frames', {}):
                (OUT / f"{row['index']}.plist").write_bytes(payload)
                frame_matches.append(dict(frame=data['frames'][alias['value']], metadata=data['metadata'],
                    source=dict(member=pack['member'], entry=row, sha256=hashlib.sha256(payload).hexdigest())))
    if len(frame_matches) != 1:
        raise ValueError(f'Expected exact unique frame, found {len(frame_matches)}')
    vt = parse_table((OUT/'vt.table').read_bytes())
    pages = {r[1]: r for r in vt['records']}
    names = {r['key']: r['name'] for r in vt['names']}
    x, y, width, height = mapping[0]['value']
    if not (0 < width <= 16 and 0 < height <= 16):
        raise ValueError('Unbounded portrait dimensions')
    canvas = Image.new('RGBA', (width*124, height*124))
    tiles = []
    for dy in range(height):
        for dx in range(width):
            address = (y+dy)*512+x+dx
            level, _, offset, key = pages[address]
            if level != 0:
                raise ValueError('Unsupported mip')
            raw = OUT/f'{address}.bin'
            source = extract(apk, catalogue, f'packed_png/vt_data/astc/{names[key]}/{offset}', raw, APK_SHA256)
            payload = raw.read_bytes()
            if len(payload) != 16384:
                raise ValueError('Unexpected ASTC tile size')
            ktx = raw.with_suffix('.ktx')
            ktx.write_bytes(IDENTIFIER + struct.pack('<13I', 0x04030201, 0, 1, 0,
                0x93B0, 0x1908, 128, 128, 0, 0, 1, 1, 0) + struct.pack('<I', len(payload)) + payload)
            decoded = convert([ktx], OUT/f'decoded-{address}', DEFAULT_DECODER)['textures'][0]['outputs'][0]
            with Image.open(ROOT/decoded['png']) as image:
                canvas.paste(image.convert('RGBA').crop((2,2,126,126)), (dx*124,dy*124))
            tiles.append(dict(address=address, source=source, decoded=decoded))
    frame = frame_matches[0]['frame']
    fx, fy, fw, fh = map(int, re.findall(r'-?\d+', frame['frame']))
    sx, sy, sw, sh = map(int, re.findall(r'-?\d+', frame['sourceColorRect']))
    source_size = tuple(map(int, re.findall(r'\d+', frame['sourceSize'])))
    left, top = fx-x*124, fy-y*124
    cw, ch = (fh, fw) if frame['rotated'] else (fw, fh)
    if not (0 <= left < left+cw <= canvas.width and 0 <= top < top+ch <= canvas.height):
        raise ValueError('Sprite crop outside mapped tiles')
    sprite = canvas.crop((left,top,left+cw,top+ch))
    if frame['rotated']:
        sprite = sprite.transpose(Image.Transpose.ROTATE_90)
    if sprite.size != (sw, sh) or not (0 <= sx <= sx+sw <= source_size[0] and 0 <= sy <= sy+sh <= source_size[1]):
        raise ValueError('Trim rectangle inconsistent')
    portrait = Image.new('RGBA', source_size)
    portrait.paste(sprite, (sx, sy))
    output = OUT/(stem+'.png')
    portrait.save(output)
    report = dict(apk_sha256=APK_SHA256, **(provenance or {}), logical=logical, alias=alias,
        mapping=mapping[0], vt_sources=sources, scanned_metadata_candidates=scanned,
        frame=frame_matches[0], tiles=tiles, output=str(output.relative_to(ROOT)),
        output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), size=source_size,
        evidence_kind='Local static extraction and VT reconstruction, not original runtime evidence',
        assumptions=['ASTC 4x4 LDR linear', '512-column virtual grid with 124-pixel stride and 2-pixel tile border',
            'Runtime colour profile not verified'])
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', choices=('monster', 'player', 'breakdown'), default='monster')
    parser.add_argument('--id', type=int, help='character/monster table id (default 1 / 991)')
    args = parser.parse_args()
    main(args.actor, args.id)
