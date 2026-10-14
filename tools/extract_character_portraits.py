"""Reproduce three named CharImage PNGs from APK hashes, never visual guesses."""
from pathlib import Path
import argparse
import hashlib
import json

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from inspect_neox_model import extract_npk_entry
from neox_resource_paths import lookup_logical, read_catalogue
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {1: (4995, 'elsa'), 2: (5664, 'lynn'), 3: (3395, 'mirai')}


def run(apk: Path, out: Path):
    with apk.open('rb') as stream:
        apk_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    if apk_sha256 != APK_SHA256:
        raise ValueError('APK SHA-256 differs from investigated source')
    catalogue = read_catalogue(apk)
    table_path = ROOT/'analysis/game-data/characters.json'
    table = json.loads(table_path.read_text('utf8'))
    out.mkdir(parents=True, exist_ok=True)
    inputs, provenance = [], []
    for row in table['rows']:
        if row['id'] not in EXPECTED:
            continue
        expected_index, slug = EXPECTED[row['id']]
        logical_path = row['fields']['CharImage']
        if not logical_path.endswith('.png'):
            raise ValueError('unexpected character portrait suffix')
        archive_path = logical_path[:-4] + '.pkm'
        matches = lookup_logical(catalogue, archive_path)
        if len(matches) != 1 or matches[0]['index'] != expected_index:
            raise ValueError('portrait mapping differs from validated APK')
        match = matches[0]
        path = out/f'{slug}.CharImage.ktx'
        source = extract_npk_entry(apk, match['member'], match['index'], path)
        inputs.append(path)
        provenance.append({**source, 'apk_sha256': apk_sha256, 'sample_path': str(path.resolve()),
                           'character_id': row['id'], 'english_name': row['fields']['ENGLISH_NAME'],
                           'logical_path': logical_path, 'archive_logical_path': archive_path,
                           'field': 'CharImage', 'script_source': table['source'],
                           'field_source': row['field_sources']['CharImage'],
                           'table_sha256': hashlib.sha256(table_path.read_bytes()).hexdigest()})
    if len(inputs) != 3:
        raise ValueError('missing requested character rows')
    provenance_path = out/'provenance.json'
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf8')
    result = convert(inputs, out, DEFAULT_DECODER, provenance_path=provenance_path,
                     inspector=DEFAULT_INSPECTOR)
    records = []
    for texture in result['textures']:
        p = texture['provenance']
        records.append({'character_id': p['character_id'], 'english_name': p['english_name'],
                        'logical_path': p['logical_path'], 'archive_logical_path': p['archive_logical_path'],
                        'member': p['member'], 'index': p['index'], 'name_hash': p['name_hash'],
                        'source_sha256': p['sha256'], **texture['outputs'][0]})
    (out/'portraits.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf8')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    parser.add_argument('--out', type=Path, default=ROOT/'analysis/resource-mapping/characters')
    args = parser.parse_args()
    print(json.dumps(run(args.apk, args.out), ensure_ascii=False, indent=2))
