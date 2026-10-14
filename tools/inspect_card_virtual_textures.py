"""Record source card-to-VT links and bounded raw page-table structure.

Does not assign unproven semantics to the four-word VT records or decode art.
"""
import hashlib
import json
import struct
from pathlib import Path
from neox_resource_paths import parse_vt_config, read_catalogue, lookup_logical
from export_elsa_model import extract, write_json
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]


def parse_table(data):
    if len(data) < 8:
        raise ValueError('truncated table')
    version, count = struct.unpack_from('<II', data)
    if version != 0 or count != 47:
        raise ValueError('unrecognized observed table header')
    pos, names = 8, []
    for _ in range(count):
        if pos + 8 > len(data):
            raise ValueError('truncated name header')
        key, length = struct.unpack_from('<II', data, pos)
        pos += 8
        if not 0 < length <= 4096 or pos + length > len(data):
            raise ValueError('name length out of bounds')
        value = data[pos:pos+length]
        if not value.endswith(b'\0'):
            raise ValueError('missing observed NUL terminator')
        name, _, padding = value.partition(b'\0')
        if not name or any(padding):
            raise ValueError('invalid name terminator padding')
        names.append(dict(key=key, name=name.decode('ascii'), offset=pos))
        pos += length
    if len({n['key'] for n in names}) != count:
        raise ValueError('duplicate names key')
    records = struct.unpack_from('<I', data, pos)[0]
    pos += 4
    if records > 100000 or pos + records * 16 != len(data):
        raise ValueError('record table does not exactly consume payload')
    return dict(version=version, names=names, record_count=records, records_offset=pos,
                records=[list(struct.unpack_from('<4I', data, pos+i*16)) for i in range(records)],
                semantics='Four uint32 words per record; field meanings unresolved')


def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != APK_SHA256:
        raise ValueError('APK identity mismatch')
    out = ROOT/'analysis/card-art'
    catalogue = read_catalogue(apk)
    sources = {}
    for path in ['packed_png/vt_data/vt.table', 'packed_png/vt_data/vt_config.jsondata']:
        sources[path] = extract(apk, catalogue, path, out/Path(path).name, digest)
    vt = parse_vt_config((out/'vt_config.jsondata').read_bytes())
    table = parse_table((out/'vt.table').read_bytes())
    write_json(out/'vt-table-raw.json', table)
    # Native Thumb loader d32e7e..d32eaa reads words 0..2, then a halfword
    # at +12, and writes ((word2 >> 14) & 511) | (halfword3 << 9).
    names = {n['key']: n['name'] for n in table['names']}
    groups = {}
    seen = set()
    for ordinal, (level, address, offset, name_key) in enumerate(table['records']):
        if level != 0 or name_key not in names or (level, address) in seen:
            raise ValueError('Observed source page-table invariants changed')
        seen.add((level, address))
        groups.setdefault(name_key, []).append((ordinal, address, offset))
    for group in groups.values():
        if len(group) != 256 or [r[2] for r in group] != list(range(16384, 4194305, 16384)):
            raise ValueError('Observed 256-entry group stride changed')
    write_json(out/'vt-table-index-evidence.json', dict(
        evidence_kind='Local static disassembly and byte correlation; no target execution',
        source_table_sha256=hashlib.sha256((out/'vt.table').read_bytes()).hexdigest(),
        native_source_sha256=hashlib.sha256((ROOT/'analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so').read_bytes()).hexdigest(),
        instruction_range=['0xd32e7e', '0xd32eaa'],
        index_expression='((word2 >> 14) & 0x1ff) | ((word3 & 0xffff) << 9), stored as uint16',
        groups=[dict(name_key=k, name=names[k], count=len(v), first_record=v[0], last_record=v[-1]) for k,v in groups.items()],
        unresolved=['Meaning of virtual address word and texture coordinate correspondence',
                    'Whether word2 denotes end offset or another address encoding',
                    'Physical tile path construction, codec and tile dimensions']))
    paths = {r['key'].lower(): r for r in vt['fullPathToPng']}
    pages = {r['key'].lower(): r for r in vt['pngsToPageID']}
    cards_path = ROOT/'analysis/first-encounter/player-cards.json'
    cards = json.loads(cards_path.read_text('utf8'))
    rows = []
    for card in cards['rows']:
        path = card['fields']['CHARACTER_IMAGE']
        mapping = paths[path.lower()]
        page = pages[mapping['value'].lower()]
        rows.append(dict(card_id=card['id'], name=card['fields']['NAME'], logical_image=path,
                         full_path_mapping=mapping, page_mapping=page,
                         direct_resource_matches=lookup_logical(catalogue, path)))
    report = dict(evidence_kind='Local static extraction; not REA Evidence or runtime observation',
                  apk_sha256=digest, sources=sources, card_table_source=cards['source'],
                  input_card_json_sha256=hashlib.sha256(cards_path.read_bytes()).hexdigest(), cards=rows,
                  table_summary=dict(names=len(table['names']), records=table['record_count'],
                                     bytes=len((out/'vt.table').read_bytes())),
                  unresolved=['VT four-word record semantics and tile filenames',
                              'Block codec/size and source crop/rotation reconstruction',
                              'Actual card image reconstruction and visual identity validation'])
    write_json(out/'card-vt-links.json', report)
    print(json.dumps(dict(cards=rows, table=report['table_summary']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
