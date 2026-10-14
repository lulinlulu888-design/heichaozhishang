"""Look for exact cube object/media IDs in every loose APK BNK.

Only parses bounded chunk/record envelopes; no event-action or codec semantics.
"""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import chunks, sha


def objects(payload):
    if len(payload) < 4:
        raise ValueError('missing HIRC count')
    count = struct.unpack_from('<I', payload)[0]
    cursor = 4
    records = []
    if count > 100000:
        raise ValueError('HIRC count exceeds bound')
    for _ in range(count):
        if cursor + 9 > len(payload):
            raise ValueError('truncated HIRC record')
        kind, size, ident = struct.unpack_from('<BII', payload, cursor)
        if size < 4 or cursor + 5 + size > len(payload):
            raise ValueError('invalid HIRC size')
        records.append(dict(type=kind, id=ident, offset=cursor, bytes=size+5))
        cursor += 5+size
    if cursor != len(payload):
        raise ValueError('HIRC trailing bytes')
    return records


def main():
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK mismatch')
    out = ROOT/'analysis/battle-visual/enemy-audio'
    metadata_path = out/'SoundbanksInfo.xml'
    if sha(metadata_path.read_bytes()) != 'b678fee4ae4f4e4e16e0bc71eadc2af37ae6bc980a6b73dc1117a674d1b483f2':
        raise ValueError('metadata mismatch')
    banks = ET.parse(metadata_path).findall('.//SoundBank')
    cube = next(b for b in banks if b.findtext('ShortName') == 'm_mofang')
    event_ids = {int(e.get('Id')) for e in cube.findall('IncludedEvents/Event')}
    media_ids = {int(e.get('Id')) for e in cube.findall('IncludedMemoryFiles/File')}
    metadata = {int(b.get('Id')): b for b in banks}
    rows = []
    with zipfile.ZipFile(APK) as archive:
        members = sorted(n for n in archive.namelist() if n.endswith('.bnk'))
        for name in members:
            raw = archive.read(name)
            row = dict(member=name, sha256=sha(raw), bytes=len(raw))
            try:
                parts = chunks(raw)
                version, bank_id = struct.unpack_from('<II', parts[b'BKHD'][1])
                records = objects(parts[b'HIRC'][1]) if b'HIRC' in parts else []
                index = parts.get(b'DIDX', (0, b''))[1]
                if len(index) % 12:
                    raise ValueError('invalid DIDX size')
                media = list(struct.iter_unpack('<III', index))
                data = parts.get(b'DATA', (0, b''))[1]
                if any(offset+size > len(data) for _, offset, size in media):
                    raise ValueError('media outside DATA')
                declared = metadata.get(bank_id)
                expected = set() if declared is None else {
                    int(e.get('Id')) for e in declared.findall('IncludedEvents/Event')}
                ids = {r['id'] for r in records}
                row.update(version=version, bank_id=bank_id, object_count=len(records),
                           media_count=len(media), cube_objects=[r for r in records if r['id'] in event_ids],
                           cube_media=[dict(id=i,offset=o,bytes=s) for i,o,s in media if i in media_ids],
                           declared_event_count=len(expected), declared_event_ids_found=len(expected & ids),
                           missing_declared_event_ids=sorted(expected-ids), parsed=True)
            except (ValueError, KeyError, struct.error) as error:
                row.update(parsed=False, error=str(error))
            rows.append(row)
    report = dict(apk_sha256=APK_SHA256, metadata_sha256=sha(metadata_path.read_bytes()),
                  bank_count=len(rows), parsed_count=sum(r['parsed'] for r in rows),
                  target_event_ids=sorted(event_ids), target_media_ids=sorted(media_ids), banks=rows,
                  limitations=['Exact object IDs in HIRC and media IDs in DIDX only.',
                               'All loose .bnk members; unparsed, aliased, packed or renamed media remain unknown.',
                               'Matching ID alone is not proof of playback routing or audio identity.',
                               'Static local parser evidence, not REA/runtime evidence.'])
    (out/'merged-bank-scan.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(banks=len(rows), parsed=report['parsed_count'],
                          cube_object_matches=sum(len(r.get('cube_objects',[])) for r in rows),
                          cube_media_matches=sum(len(r.get('cube_media',[])) for r in rows))))
    if report['parsed_count'] != len(rows):
        raise SystemExit('Partial coverage; inspect errors')


if __name__ == '__main__':
    main()
