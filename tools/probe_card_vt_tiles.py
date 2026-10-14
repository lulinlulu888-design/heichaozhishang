"""Extract source-linked VT tiles and render a candidate assembly for inspection.

128px physical tiles and 124px virtual stride are observed in native code.
ASTC 4x4, a two-pixel border and row-major mapping are hypotheses checked by
block validation and the output image, not a claim of original UI fidelity.
"""
import hashlib
import json
import re
import struct
from pathlib import Path
from PIL import Image
from decode_ktx import IDENTIFIER, convert, DEFAULT_DECODER
from export_elsa_model import extract, write_json
from extract_texture_samples import APK_SHA256
from inspect_card_virtual_textures import parse_table
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]


def main():
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    out = ROOT/'analysis/card-art/tile-probe'
    catalogue = read_catalogue(apk)
    table = parse_table((ROOT/'analysis/card-art/vt.table').read_bytes())
    names = {n['key']: n['name'] for n in table['names']}
    pages = {r[1]: r for r in table['records']}
    cards = json.loads((ROOT/'analysis/card-art/card-vt-links.json').read_text('utf8'))['cards']
    frames = {r['card_id']: r for r in json.loads((ROOT/'analysis/card-art/sprite-frames.json').read_text('utf8'))['frames']}
    report = []
    for card in cards:
        x, y, width, height = card['page_mapping']['value']
        canvas = Image.new('RGBA', (width*124, height*124))
        tiles = []
        for dy in range(height):
            for dx in range(width):
                address = (y+dy)*512+x+dx
                level, _, offset, name_key = pages[address]
                if level != 0:
                    raise ValueError('Unexpected layer')
                logical = f'packed_png/vt_data/astc/{names[name_key]}/{offset}'
                raw = out/f'{address}.bin'
                source = extract(apk, catalogue, logical, raw, APK_SHA256)
                payload = raw.read_bytes()
                if len(payload) != 16384:
                    raise ValueError('Unexpected physical tile length')
                # Synthetic decoder wrapper, explicitly not an original KTX header.
                ktx = raw.with_suffix('.ktx')
                ktx.write_bytes(IDENTIFIER + struct.pack('<13I', 0x04030201,
                    0, 1, 0, 0x93B0, 0x1908, 128, 128, 0, 0, 1, 1, 0)
                    + struct.pack('<I', len(payload)) + payload)
                decoded = convert([ktx], out/f'decoded-{address}', DEFAULT_DECODER)
                image_record = decoded['textures'][0]['outputs'][0]
                with Image.open(ROOT/image_record['png']) as image:
                    canvas.paste(image.convert('RGBA').crop((2, 2, 126, 126)), (dx*124, dy*124))
                tiles.append(dict(address=address, source=source, decoded=image_record))
        destination = out/f"card-{card['card_id']}-candidate.png"
        canvas.save(destination)
        frame = frames[card['card_id']]
        metadata = frame['frame']
        if metadata['rotated'] or metadata['sourceColorRect'] != '{{0,0},{286,286}}' or metadata['sourceSize'] != '{286,286}':
            raise ValueError('Unimplemented sprite rotation/trim variant')
        fx, fy, fw, fh = map(int, re.findall(r'-?\d+', metadata['frame']))
        left, top = fx-x*124, fy-y*124
        if not (0 <= left < left+fw <= canvas.width and 0 <= top < top+fh <= canvas.height):
            raise ValueError('Source frame outside mapped tile rectangle')
        sprite = out/f"card-{card['card_id']}.png"
        canvas.crop((left, top, left+fw, top+fh)).save(sprite)
        report.append(dict(card_id=card['card_id'], name=card['name'], mapping=card['page_mapping'],
                           png=str(destination.relative_to(ROOT)), tiles=tiles,
                           sprite=str(sprite.relative_to(ROOT)), sprite_frame=frame,
                           sprite_sha256=hashlib.sha256(sprite.read_bytes()).hexdigest(),
                           png_sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
    write_json(out/'manifest.json', dict(evidence_kind='Local static extraction and candidate pixel assembly',
        assumptions=['ASTC 4x4 LDR linear decode', 'Row-major virtual grid width 512',
                     'Two-pixel border on each physical tile', 'Original runtime colour profile not verified'], cards=report))
    print(json.dumps([dict(card_id=r['card_id'], png=r['png']) for r in report]))


if __name__ == '__main__':
    main()
