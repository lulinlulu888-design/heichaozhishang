"""Bounded data-only search of the APK's scene pack for a known scene name."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET

from neox_resource_paths import lookup_logical

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual'


def main():
    catalogue = json.loads((ROOT / 'analysis/resource-mapping/npk-indices.json').read_text())
    pack, = [p for p in catalogue if p['member'] == 'assets/res/scene.npk']
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    matches = []
    inspected = 0
    OUT.mkdir(exist_ok=True)
    with zipfile.ZipFile(apk) as archive, archive.open(pack['member']) as stream:
        for row in sorted(pack['entries'], key=lambda r: r['offset']):
            if row['encryption'] or row['compression'] not in (0, 1):
                raise ValueError('Unsupported scene pack entry')
            if row['original_size'] > 64 * 1024 * 1024:
                raise ValueError('Entry exceeds inspection budget')
            stream.seek(row['offset'])
            raw = stream.read(row['stored_size'])
            if len(raw) != row['stored_size']:
                raise ValueError('Truncated entry')
            if row['compression']:
                decoder = zlib.decompressobj()
                data = decoder.decompress(raw, row['original_size'] + 1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('Invalid compressed entry')
            else:
                data = raw
            if len(data) != row['original_size']:
                raise ValueError('Decoded size mismatch')
            inspected += 1
            if b'city_battle_3' not in data.lower():
                continue
            target = OUT / f'scene-{row["index"]:05d}.bin'
            target.write_bytes(data)
            strings = [s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{8,}', data)
                       if b'city_battle_3' in s.lower() or b'camera_1' in s.lower()]
            matches.append({'entry': row, 'sha256': hashlib.sha256(data).hexdigest(),
                            'output': target.relative_to(ROOT).as_posix(), 'strings': strings})
    report = {'scope': 'Decoded bytes of scene.npk only; substring matches are references, not proven scene identity',
              'member': pack['member'], 'index_sha256': pack['index_sha256'],
              'inspected': inspected, 'matches': matches}
    (OUT / 'scene-payload-search.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    identity = 'scene/chess_xuzhang/chess_xuzhang.scn'
    identity_matches = lookup_logical(catalogue, identity)
    if len(identity_matches) != 1:
        raise ValueError('Prologue scene identity is ambiguous')
    selected, = [m for m in matches if m['entry']['index'] == identity_matches[0]['index']]
    scene = ET.fromstring((ROOT / selected['output']).read_bytes())
    files = [{'id': e.tag, 'path': e.attrib['Path'],
              'matches': lookup_logical(catalogue, e.attrib['Path'])}
             for e in scene.find('.//AllFiles')]
    manifest = {'identity': identity, 'identity_matches': identity_matches,
                'source_sha256': selected['sha256'],
                'cameras': [e.attrib for e in scene.iter('Camera')],
                'models': [e.attrib for e in scene.iter('model')],
                'effects': [e.attrib for e in scene.iter('sfx')], 'files': files,
                'limitation': 'Scene-level references only; model mesh/material/texture dependencies not yet traversed or rendered.'}
    (OUT / 'prologue-scene-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(json.dumps({'inspected': inspected, 'matches': len(matches),
                      'entries': [m['entry']['index'] for m in matches]}))


if __name__ == '__main__':
    main()
