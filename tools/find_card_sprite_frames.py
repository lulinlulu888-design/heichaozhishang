"""Find exact card sprite metadata in APK plist payloads, without filename guesses."""
import hashlib
import json
import plistlib
import zipfile
from pathlib import Path
from extract_npk import decode_entry
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue
from export_elsa_model import write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    cards = json.loads((ROOT/'analysis/card-art/card-vt-links.json').read_text('utf8'))['cards']
    wanted = {c['full_path_mapping']['value']: c['card_id'] for c in cards}
    pack = next(p for p in read_catalogue(apk) if p['member'] == 'assets/res/packed_png.npk')
    found, scanned = [], 0
    with zipfile.ZipFile(apk) as archive, archive.open(pack['member']) as stream:
        for row in sorted(pack['entries'], key=lambda r: r['offset']):
            # Exclude observed physical VT tiles; metadata stays bounded.
            if row['original_size'] == 16384 or row['original_size'] > 4*1024*1024:
                continue
            stream.seek(row['offset'])
            payload = decode_entry(stream.read(row['stored_size']), {**row, 'offset': 0}, max_decoded_bytes=4*1024*1024)
            scanned += 1
            if not payload.lstrip().startswith((b'<?xml', b'<plist')) or b'<plist' not in payload[:300]:
                continue
            data = plistlib.loads(payload)
            for name, card_id in wanted.items():
                if name in data.get('frames', {}):
                    out = ROOT/f"analysis/card-art/plists/{row['index']}.plist"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(payload)
                    found.append(dict(card_id=card_id, name=name, frame=data['frames'][name],
                        metadata=data['metadata'], source=dict(apk_sha256=APK_SHA256,
                        member=pack['member'], entry=row, sha256=hashlib.sha256(payload).hexdigest())))
    if sorted(r['card_id'] for r in found) != sorted(wanted.values()):
        raise ValueError(f'Expected one exact frame per card; found {[r["card_id"] for r in found]}')
    write_json(ROOT/'analysis/card-art/sprite-frames.json', dict(scanned=scanned, frames=found))
    print(json.dumps(found, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
