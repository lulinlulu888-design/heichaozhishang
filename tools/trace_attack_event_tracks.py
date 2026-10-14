"""Recover original Elsa event ratios and preserve the relevant state-machine trace.

Seconds are derived using sampled ACL duration, not observed engine timestamps.
Combat timing and playback timers remain separate until their callers are traced.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import inspect_battle_rules as static
from export_elsa_model import write_json, extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/skill-animation'


def main():
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    source = extract(apk, read_catalogue(apk), 'character/player/ailisha/ailisha.ags', OUT/'ailisha.ags', APK_SHA256)
    if source['sha256'] != '12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729':
        raise ValueError('Observed event-track source changed')
    tracks = ET.fromstring((OUT/'ailisha.ags').read_bytes()).find('AnimationEventTracks')
    if tracks.attrib.get('Version') != '2':
        raise ValueError('Unsupported animation-event version')
    mapping = json.loads((OUT/'mapping.json').read_text('utf8'))
    clips = {}
    for name, metadata in mapping['clips'].items():
        track = tracks.find('EventTrack_'+name)
        if track is None:
            raise ValueError(f'Missing event track: {name}')
        rows = []
        for event in track:
            ratio = float(event.attrib['TimeRatio'])
            if not 0 <= ratio <= 1:
                raise ValueError('Event ratio outside clip')
            rows.append(dict(name=event.attrib['Name'], ratio_literal=event.attrib['TimeRatio'],
                time_ratio=ratio, derived_seconds=ratio*metadata['duration_seconds']))
        if len({r['name'] for r in rows}) != len(rows):
            raise ValueError('Duplicate event names need native lookup semantics')
        clips[name] = dict(duration_seconds=metadata['duration_seconds'], events=rows)
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    modules = [(6025, ('_enterLogic', '_playNext', 'playSingleAnimation', '_realPlayAnimation', 'getAnimReactCount', 'onEventAnimEnd')),
               (2072, ('getAnimationListInTimelineData', 'getSkillDurationAndReactTimeList')),
               (8905, ('getAnimationEventTime', 'getAnimationLength')),
               (8067, ('getRealAnimNameByType',)), (7522, ()), (9615, ())]
    for identity, names in modules:
        row = next(r for r in index if r['index'] == identity)
        write_json(OUT/f'{identity}-timing.json', static.export(row, names))
    result = dict(evidence_kind='Original XML event data plus hash-checked partial script instructions',
        source=source, clips=clips,
        findings=['SkillHelper random.choice branch is gated by len(retAnimList)==1',
                  'SkillState uses jump_next to shorten the endPlayerFocus timer when useJump is true, not the clip itself',
                  'onEventAnimEnd calls _playNext; two single-hit clips satisfy reactCount=2 before the third list entry',
                  'CompAnimation maps the type name then asks Model for event milliseconds and divides by 1000'],
        unresolved=['Native TimeRatio to milliseconds conversion',
                    'Original native-client timing and full player-focus/effect implementation',
                    'No original-client runtime or new rendered battle validation'])
    write_json(OUT/'event-tracks.json', result)
    print(json.dumps({name:[r for r in c['events'] if r['name'] in ['attack','jump_next']] for name,c in clips.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
