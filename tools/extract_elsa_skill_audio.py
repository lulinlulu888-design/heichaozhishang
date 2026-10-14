"""Extract original Elsa WEM payloads without executing or transcoding them."""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import chunks, sha
from scan_enemy_audio_banks import objects


def main():
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    metadata = ROOT/'analysis/battle-visual/enemy-audio/SoundbanksInfo.xml'
    if sha(metadata.read_bytes()) != 'b678fee4ae4f4e4e16e0bc71eadc2af37ae6bc980a6b73dc1117a674d1b483f2':
        raise ValueError('metadata identity changed')
    bank_info = next(b for b in ET.parse(metadata).findall('.//SoundBank')
                     if b.findtext('ShortName') == 'ailisha_skill')
    member = 'assets/res/wwise/ailisha_skill.bnk'
    with zipfile.ZipFile(APK) as archive:
        raw = archive.read(member)
    parts = chunks(raw)
    version, ident = struct.unpack_from('<II', parts[b'BKHD'][1])
    if version != 120 or ident != int(bank_info.get('Id')):
        raise ValueError('bank metadata mismatch')
    records = objects(parts[b'HIRC'][1])
    event_ids = {int(e.get('Id')) for e in bank_info.findall('IncludedEvents/Event')}
    if not event_ids <= {r['id'] for r in records}:
        raise ValueError('missing declared event')
    names = {int(f.get('Id')): f.findtext('ShortName')
             for f in bank_info.findall('IncludedMemoryFiles/File')}
    out = ROOT/'analysis/battle-visual/elsa-audio'
    out.mkdir(parents=True, exist_ok=True)
    (out/'ailisha_skill.bnk').write_bytes(raw)
    rows = []
    data_offset, data = parts[b'DATA']
    index = parts[b'DIDX'][1]
    if len(index) % 12:
        raise ValueError('invalid index')
    seen = set()
    for media_id, offset, size in struct.iter_unpack('<III', index):
        if offset+size > len(data) or media_id in seen or media_id not in names:
            raise ValueError('media range/identity mismatch')
        seen.add(media_id)
        payload = data[offset:offset+size]
        if payload[:4] != b'RIFF' or payload[8:12] != b'WAVE':
            raise ValueError('unexpected media header')
        if struct.unpack_from('<I', payload, 4)[0]+8 != len(payload):
            raise ValueError('RIFF length mismatch')
        sections = chunks(payload, 12)
        format_tag, channels, rate = struct.unpack_from('<HHI', sections[b'fmt '][1])
        (out/f'{media_id}.wem').write_bytes(payload)
        rows.append(dict(id=media_id, source_name=names[media_id], bytes=size,
                         bank_offset=data_offset+offset, sha256=sha(payload),
                         format_tag=format_tag, channels=channels, sample_rate=rate))
    if seen != set(names):
        raise ValueError('media set differs from metadata')
    report = dict(apk_sha256=APK_SHA256, member=member, bank_sha256=sha(raw), version=version,
                  events=[e.attrib for e in bank_info.findall('IncludedEvents/Event')], media=rows,
                  limitations=['WEM containers extracted exactly; compressed audio not decoded or auditioned.',
                               'No event-to-media routing inferred from similar names.',
                               'No client integration or original runtime verification.',
                               'Ordinary local static evidence, not REA evidence.'])
    (out/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(bank_sha256=sha(raw), events=len(event_ids), media=len(rows),
                          format_tags=sorted({r['format_tag'] for r in rows}))))


if __name__ == '__main__':
    main()
