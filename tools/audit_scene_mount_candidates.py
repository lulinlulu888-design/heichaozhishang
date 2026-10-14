"""Check all path splits against every APK NPK; matches are candidates, not identity proof."""
import hashlib
import json
from pathlib import Path
from extract_game_data import export_table
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, resource_hash

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/scene-inventory/mount-candidates.json'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    catalogue = read_catalogue(apk)
    by_hash = {}
    for pack in catalogue:
        for entry in pack['entries']:
            by_hash.setdefault(entry['name_hash'], []).append(dict(member=pack['member'], **entry))
    table = export_table(9650)
    paths = sorted({r['fields']['ScenePath'] for r in table['rows'] if r['fields'].get('ScenePath')})
    results = []
    for path in paths:
        parts = path.replace('\\', '/').split('/')
        variants = []
        for count in range(len(parts)):
            relative = '/'.join(parts[count:])
            value = resource_hash(relative)
            variants.append(dict(mountPrefix='/'.join(parts[:count]), remainingPath=relative,
                                 hash=f'{value:08x}', matches=by_hash.get(value, [])))
        results.append(dict(path=path, variants=variants))
    tutorial, = [r for r in results if r['path'] == 'scene/city_battle_3/city_battle_3.scn']
    report = dict(evidence='Static APK index comparison; no runtime mount state', apkSha256=APK_SHA256,
        packCount=len(catalogue), pathCount=len(paths),
        queryCount=sum(len(r['variants']) for r in results),
        matchedPathCount=sum(any(v['matches'] for v in r['variants']) for r in results),
        tutorial=tutorial, rows=results,
        limitations=['Every nonempty suffix is checked against every pack, ignoring runtime mount bounds and ordering.',
                     'Hash matches alone do not establish payload identity. No extension or case rewriting is assumed.',
                     'Missing matches do not rule out external patches, loose files or untraced backend transformations.'])
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({k: report[k] for k in ('packCount','pathCount','queryCount','matchedPathCount','tutorial')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
