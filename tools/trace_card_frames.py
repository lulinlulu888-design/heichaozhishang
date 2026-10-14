"""Hash-checked static card UI wiring and bounded atlas-member search; no game execution."""
import hashlib
import argparse
import json
import plistlib
import zipfile
from pathlib import Path
import inspect_battle_rules as static
from extract_npk import decode_entry
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packed-png', action='store_true')
    args = parser.parse_args()
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    for number in (4644, 6992, 9176, 9257):
        report = static.export(next(r for r in index if r['index'] == number))
        (OUT/f'card-script-{number}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    member = 'assets/res/packed_png.npk' if args.packed_png else 'assets/res/uires.npk'
    pack = next(p for p in read_catalogue(apk) if p['member'] == member)
    limit = 2*1024*1024
    scanned, skipped, matches, errors = 0, [], [], []
    with zipfile.ZipFile(apk) as z, z.open(pack['member']) as stream:
        for entry in sorted(pack['entries'], key=lambda e:e['offset']):
            if max(entry['stored_size'], entry['original_size']) > limit:
                skipped.append(entry['index'])
                continue
            stream.seek(entry['offset'])
            try:
                data = decode_entry(stream.read(entry['stored_size']), dict(entry, offset=0), max_decoded_bytes=limit)
            except Exception as error:
                errors.append(dict(index=entry['index'], error=str(error)))
                continue
            scanned += 1
            if not any(marker in data for marker in (b'bg_atk.png', b'bg_atk_s.png', b'bg_skill_s.png', b'bg_def_s.png', b'cost_s1.png', b'cost_normal.png')):
                continue
            row = dict(entry=entry, sha256=hashlib.sha256(data).hexdigest())
            try:
                plist = plistlib.loads(data)
                row['frames'] = {k:v for k,v in plist['frames'].items() if k.startswith('card/') and '/face/' not in k}
                row['metadata'] = plist['metadata']
                (OUT/f"card-atlas-{entry['index']}.plist").write_bytes(data)
            except Exception:
                row['kind'] = 'marker only; not a parsed atlas'
            matches.append(row)
    report = dict(apk_sha256=APK_SHA256, member=pack['member'], index_sha256=pack['index_sha256'],
        decoded_entries=scanned, size_limit=limit, skipped_indices=skipped, errors=errors, matches=matches,
        limitation='Static local evidence only. Atlas texture identity and runtime card rendering not established.')
    (OUT/('card-frame-search-packed.json' if args.packed_png else 'card-frame-search.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(decoded=scanned, skipped=len(skipped), errors=len(errors), matches=[m['entry']['index'] for m in matches])))


if __name__ == '__main__':
    main()
