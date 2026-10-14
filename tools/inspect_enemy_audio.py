"""Extract the source-named cube bank and validate its embedded media inventory.

Static local evidence only. Does not infer event routing from similar filenames.
"""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_neox_model import extract_npk_entry
from neox_resource_paths import lookup_logical, read_catalogue


def sha(data):
    return hashlib.sha256(data).hexdigest()


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    result = {}
    cursor = start
    while cursor < end:
        if cursor + 8 > end:
            raise ValueError('truncated chunk header')
        tag, size = struct.unpack_from('<4sI', data, cursor)
        stop = cursor + 8 + size
        if stop > end or tag in result:
            raise ValueError('invalid/duplicate chunk')
        result[tag] = (cursor + 8, data[cursor + 8:stop])
        cursor = stop
    return result


def main():
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    out = ROOT/'analysis/battle-visual/enemy-audio'
    out.mkdir(parents=True, exist_ok=True)
    info_path = out/'SoundbanksInfo.xml'
    info_source = extract_npk_entry(APK, 'assets/res/wwise.npk', 24, info_path)
    reference = ROOT/'analysis/assets/portability/wwise.00024.XML.bin'
    if info_path.read_bytes() != reference.read_bytes():
        raise ValueError('metadata source mismatch')
    banks = [b for b in ET.parse(info_path).findall('.//SoundBank')
             if b.findtext('ShortName') == 'm_mofang']
    if len(banks) != 1:
        raise ValueError('cube bank is not unique')
    bank_info = banks[0]
    member = 'assets/res/wwise/' + bank_info.findtext('Path')
    with zipfile.ZipFile(APK) as archive:
        available = set(archive.namelist())
        if member not in available:
            candidates = lookup_logical(read_catalogue(APK), 'wwise/' + bank_info.findtext('Path'))
            if candidates:
                raise ValueError('bank found inside NPK; add explicit extraction route')
            files = []
            for f in bank_info.findall('IncludedMemoryFiles/File'):
                media_member = 'assets/res/wwise/' + f.get('Id') + '.wem'
                present = media_member in available
                row = dict(id=int(f.get('Id')), short_name=f.findtext('ShortName'),
                           expected_loose_member=media_member, present=present)
                if present:
                    payload = archive.read(media_member)
                    row.update(sha256=sha(payload), bytes=len(payload))
                files.append(row)
            report = dict(apk_sha256=APK_SHA256, metadata_source=info_source,
                          expected_bank_member=member, loose_bank_present=False,
                          mounted_npk_matches=candidates,
                          events=[e.attrib for e in bank_info.findall('IncludedEvents/Event')],
                          referenced_memory_files=files,
                          limitations=['Static metadata references do not prove bank/media availability.',
                                       'Checked exact loose path and observed mounted-NPK path hash only.',
                                       'Alternate banks or encodings may contain equivalent audio; not searched.',
                                       'No audio decoded, played or added to client. Ordinary local evidence, not REA.'])
            (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps(dict(bank_present=False, events=len(report['events']),
                                  referenced_media=len(files), loose_media_present=sum(f['present'] for f in files))))
            return
        bank = archive.read(member)
    (out/'m_mofang.bnk').write_bytes(bank)
    sections = chunks(bank)
    version, bank_id = struct.unpack_from('<II', sections[b'BKHD'][1])
    if version != 120 or bank_id != int(bank_info.get('Id')):
        raise ValueError('bank header disagrees with metadata')
    data_offset, media = sections[b'DATA']
    index = sections[b'DIDX'][1]
    if len(index) % 12:
        raise ValueError('invalid media index')
    names = {int(f.get('Id')): dict(f.attrib, short_name=f.findtext('ShortName'),
                                 source_path=f.findtext('Path'))
             for f in bank_info.findall('IncludedMemoryFiles/File')}
    files = []
    seen = set()
    for media_id, offset, size in struct.iter_unpack('<III', index):
        if media_id in seen or media_id not in names or offset + size > len(media):
            raise ValueError('invalid media identity or range')
        seen.add(media_id)
        payload = media[offset:offset+size]
        if payload[:4] != b'RIFF' or payload[8:12] != b'WAVE':
            raise ValueError('media is not RIFF WAVE')
        if struct.unpack_from('<I', payload, 4)[0] + 8 != size:
            raise ValueError('RIFF length mismatch')
        parts = chunks(payload, 12)
        fmt = struct.unpack_from('<HHIIHH', parts[b'fmt '][1])
        destination = out/f'{media_id}.wem'
        destination.write_bytes(payload)
        files.append(dict(id=media_id, metadata=names[media_id], sha256=sha(payload),
                          bank_offset=data_offset+offset, bytes=size,
                          format_tag=fmt[0], channels=fmt[1], sample_rate=fmt[2]))
    if seen != set(names):
        raise ValueError('embedded media set differs from metadata')
    trigger_path = ROOT/'analysis/battle-visual/enemy-skills/enemy-music.ags'
    triggers = ET.parse(trigger_path).getroot()
    report = dict(apk_sha256=APK_SHA256, metadata_source=info_source,
                  bank=dict(member=member, sha256=sha(bank), version=version, id=bank_id),
                  events=[e.attrib for e in bank_info.findall('IncludedEvents/Event')],
                  media=files, trigger_source_sha256=sha(trigger_path.read_bytes()),
                  triggers=[dict(clip=c.tag, label=e.tag, ratio=e.get('TimeRatio'),
                                 properties=t.attrib)
                            for c in triggers.find('Triggers') for e in c for t in e],
                  limitations=['Local static parsing, not REA/runtime evidence.',
                               'ObjectFileID to bound-object mapping unresolved.',
                               'Event actions, random containers and media routing not decoded.',
                               'WEM payloads not converted or playback-tested.'])
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(bank_sha256=sha(bank), events=len(report['events']),
                          media=len(files), triggers=len(report['triggers']))))


if __name__ == '__main__':
    main()
