"""Recover the original Elsa crit_4 skeletal clip and its authored event track.

Uses the existing pinned ACL pipeline, original battle mesh and inverse binds.
Does not assign nine attack cues to eight damage states without source proof.
"""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_prologue_actor import build_source_base
from export_elsa_model import split_glb, write_json
from export_elsa_animation import encode, load_clip, validate_roundtrip
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import (file_sha256, parse_library, parse_clip,
    clip_path, extract_with_provenance, map_bones)
from neox_resource_paths import read_catalogue
from sample_lynn_idle import sample_pinned

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/elsa-ultimate'
CLIP_SHA = 'd7447d9ce4ece246d41006c64f8cf11c5acac34e3bd84aca1b87b5816bfdb271'
ACL_SHA = '22d0d328b0dacdccbed08fee3f4005021c43ebb6f8b4b7a96ddf882e9118af2b'
LIB_SHA = '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41'
AGS_SHA = '12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if file_sha256(apk) != APK_SHA256:
        raise ValueError('APK identity changed')
    library_path = ROOT / 'analysis/animation/recovered/ailisha.gisacl'
    event_path = ROOT / 'analysis/battle-visual/skill-animation/ailisha.ags'
    if file_sha256(library_path) != LIB_SHA or file_sha256(event_path) != AGS_SHA:
        raise ValueError('Original animation library or event track changed')
    library = parse_library(library_path.read_bytes())
    base, mesh_sources, bind = build_source_base()
    doc, _ = split_glb(base)
    names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
    OUT.mkdir(parents=True, exist_ok=True)
    source = extract_with_provenance(apk, read_catalogue(apk),
        clip_path('character/player/ailisha/ailisha.gisacl', 'crit_4'), OUT / 'crit_4.gisacl', APK_SHA256)
    parsed = parse_clip((OUT / 'crit_4.gisacl').read_bytes())
    if parsed['sha256'] != CLIP_SHA or parsed['acl_sha256'] != ACL_SHA:
        raise ValueError('Original ultimate animation changed')
    parsed.update(source=source, library_sha256=LIB_SHA,
                  bone_mapping=map_bones(library, parsed, names),
                  library_record=next(c for c in library['clips'] if c['name'] == 'crit_4'))
    write_json(OUT / 'crit_4.json', parsed)
    sample_pinned(OUT, {'crit_4': ACL_SHA}, 'elsa-ultimate', 1)
    clip = load_clip(OUT, 'crit_4', library, names)
    glb, animations, error = encode(base, [clip])
    validation = validate_roundtrip(base, glb, [clip])
    if not validation or validation[0]['moving_tracks'] == 0:
        raise ValueError('Original ultimate clip has no verified motion')
    (OUT / 'elsa-ultimate.glb').write_bytes(glb)
    track = ET.fromstring(event_path.read_bytes()).find('.//EventTrack_crit_4')
    if track is None:
        raise ValueError('Missing original ultimate event track')
    events = sorted([{'name': e.attrib['Name'], 'ratioLiteral': e.attrib['TimeRatio'],
                      'ratio': float(e.attrib['TimeRatio']),
                      'seconds': float(e.attrib['TimeRatio']) * parsed['duration_seconds']}
                     for e in track.findall('Event')], key=lambda e: e['ratio'])
    video = [e for e in events if e['name'] == 'video']
    attacks = [e for e in events if e['name'] == 'attack' or e['name'].startswith('attack_')]
    if len(video) != 1 or video[0]['ratioLiteral'] != '0.533333' or len(attacks) != 9:
        raise ValueError('Reviewed ultimate event structure changed')
    report = {'schema': 'hczs-elsa-ultimate-animation-v1', 'originalApkExecuted': False,
              'source': source, 'librarySha256': LIB_SHA, 'eventTrackSha256': AGS_SHA,
              'meshSources': mesh_sources, 'bindValidation': bind, 'maxBindTrsError': error,
              'animations': animations, 'verification': validation, 'events': events,
              'output': str(OUT / 'elsa-ultimate.glb'), 'sha256': hashlib.sha256(glb).hexdigest(),
              'damageCueMappingVerified': False,
              'limitations': ['Nine attack cues are not automatically nine damage receipts.',
                             'UE playback, video pause/resume, camera, VFX and audio integration remain separate.']}
    write_json(OUT / 'export-report.json', report)
    print(json.dumps({'output': report['output'], 'duration': parsed['duration_seconds'],
                      'frames': clip['frames'], 'bones': len(names), 'videoSeconds': video[0]['seconds'],
                      'attackCues': len(attacks), 'movingTracks': validation[0]['moving_tracks']}))


if __name__ == '__main__':
    main()
