"""Bounded character-pack XML scan for the recovered cube's animation event tracks.

No APK code execution. Negative results cover only the explicitly scanned entries.
"""
import hashlib
import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from extract_npk import decode_entry
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/enemy-timing'
LIMIT = 256 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--large-entries', action='store_true', help='Scan only entries above the prior 256 KiB limit, up to 32 MiB.')
    args = parser.parse_args()
    limit = 32 * 1024 * 1024 if args.large_entries else LIMIT
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    pack = next(p for p in read_catalogue(apk) if p['member'] == 'assets/res/character.npk')
    OUT.mkdir(parents=True, exist_ok=True)
    scanned, skipped, errors, tracks, candidates = 0, [], [], [], []
    previous_coverage = []
    with zipfile.ZipFile(apk) as archive, archive.open(pack['member']) as stream:
        for entry in sorted(pack['entries'], key=lambda e: e['offset']):
            size = max(entry['original_size'], entry['stored_size'])
            if args.large_entries and size <= LIMIT:
                previous_coverage.append(entry['index'])
                continue
            if size > limit:
                skipped.append(entry['index'])
                continue
            stream.seek(entry['offset'])
            stored = stream.read(entry['stored_size'])
            try:
                data = decode_entry(stored, dict(entry, offset=0), max_decoded_bytes=limit)
            except Exception as error:
                errors.append(dict(index=entry['index'], error=str(error)))
                continue
            scanned += 1
            if b'AnimationEventTracks' not in data:
                continue
            try:
                root = ET.fromstring(data)
            except ET.ParseError as error:
                errors.append(dict(index=entry['index'], error=str(error)))
                continue
            node = root.find('AnimationEventTracks')
            if node is None:
                continue
            names = [child.tag for child in node]
            row = dict(entry=entry, sha256=hashlib.sha256(data).hexdigest(), tracks=names)
            tracks.append(row)
            if 'EventTrack_fire' in names and 'EventTrack_skill_2' in names:
                path = OUT/f"candidate-{entry['index']}.xml"
                path.write_bytes(data)
                candidates.append(dict(**row, path=str(path),
                    events={child.tag: [event.attrib for event in child] for child in node}))
    report = dict(apk_sha256=APK_SHA256, member=pack['member'], index_sha256=pack['index_sha256'],
        entry_count=len(pack['entries']), decoded_entries=scanned, entry_size_limit=limit,
        previous_coverage_indices=previous_coverage,
        skipped_indices=skipped, errors=errors, event_track_files=tracks, candidates=candidates,
        scope='Candidates by clip-name overlap only; identity and native event loading not established. Other packs and larger entries not scanned.')
    (OUT/('scan-large.json' if args.large_entries else 'scan.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
    if args.large_entries:
        previous_path = OUT/'scan.json'
        previous = json.loads(previous_path.read_text('utf8'))
        if previous['apk_sha256'] != APK_SHA256 or previous['index_sha256'] != pack['index_sha256'] or previous['errors']:
            raise ValueError('Earlier scan does not prove matching successful coverage')
        large_indices = {e['index'] for e in pack['entries']} - set(previous_coverage)
        if large_indices != set(previous['skipped_indices']) or previous['decoded_entries'] != len(previous_coverage):
            raise ValueError('Scan partitions do not match')
        coverage = dict(apk_sha256=APK_SHA256, member=pack['member'], index_sha256=pack['index_sha256'],
            total_entries=len(pack['entries']), small_entries=previous['decoded_entries'], large_entries=scanned,
            partition_matches=True, errors=errors, remaining_skipped=skipped,
            all_entries_decoded=not errors and not skipped and previous['decoded_entries']+scanned == len(pack['entries']),
            reports={name: hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('scan.json', 'scan-large.json')},
            event_track_file_count=len(previous['event_track_files'])+len(tracks),
            fire_track_file_count=sum('EventTrack_fire' in r['tracks'] for r in previous['event_track_files']+tracks),
            limitation='Complete byte decoding and this XML marker scan of character.npk only; not proof of absence in other encodings, packs, or native-generated data.')
        (OUT/'coverage.json').write_text(json.dumps(coverage, indent=2), encoding='utf8')
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    script = static.export(next(r for r in index if r['index'] == 2072), ('getSkillDurationAndReactTimeList',))
    code = script['code_objects'][0]
    branch = [i for i in code['instructions'] if 426 <= i['offset'] < 487]
    if any(i['opname'] == 'UNKNOWN' for i in branch):
        raise ValueError('Unresolved opcode in fallback branch')
    expected = [(426, 'LOAD_FAST', 'nowDuration'), (429, 'LOAD_FAST', 'animLength'),
        (433, 'STORE_FAST', 'nowDuration'), (436, 'LOAD_FAST', 'findAttack'),
        (442, 'LOAD_GLOBAL', 'max'), (445, 'LOAD_FAST', 'reactTime'),
        (448, 'LOAD_CONST', 0), (454, 'STORE_FAST', 'reactTime'),
        (457, 'LOAD_FAST', 'attackTimeList'), (460, 'LOAD_ATTR', 'append'),
        (463, 'LOAD_FAST', 'nowDuration'), (466, 'LOAD_FAST', 'reactTime')]
    by_offset = {i['offset']: i for i in branch}
    for offset, op, operand in expected:
        if (by_offset[offset]['opname'], by_offset[offset].get('operand')) != (op, operand):
            raise ValueError('Fallback data flow changed')
    (OUT/'skill-helper.json').write_text(json.dumps(script, indent=2), encoding='utf8')
    (OUT/'fallback.json').write_text(json.dumps(dict(source=script['source'],
        bytecode_sha256=code['bytecode_sha256'], constant_path=code['constant_path'],
        offsets=[426, 487], branch=branch,
        derived_formula='nowDuration += animLength; if not findAttack: attackTimeList.append(nowDuration + max(reactTime, 0))',
        findings=['Earlier branches require attack or numbered attack event time > 0.',
            'When neither produces a positive event, the source appends an end-of-animation reaction.',
            'This is a conditional static reading; native event lookup results for the cube remain unknown.'],
        unchanged_client='End-of-animation enemy reaction retained; no guessed timestamp introduced.'), indent=2), encoding='utf8')
    print(json.dumps(dict(decoded=scanned, skipped=len(skipped), errors=len(errors),
        track_files=len(tracks), candidates=[r['entry']['index'] for r in candidates])))


if __name__ == '__main__':
    main()
