"""Recover Elsa's source battle entrance through the pinned NeoX/ACL pipeline.

Only offline outputs: preserve File_26 battle geometry, joints and inverse binds.
No hall skeleton, retargeting, scene edits or fabricated entrance for the cube.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from export_prologue_actor import build_source_base
from export_elsa_model import split_glb, pack_glb, write_json
from export_elsa_animation import encode, load_clip, validate_roundtrip, accessor_array
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import (file_sha256, parse_library, parse_clip,
    clip_path, extract_with_provenance, map_bones)
from neox_resource_paths import read_catalogue
from sample_lynn_idle import sample_pinned

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/entrance'
NAME = 'fight_idle_show'
CLIP_SHA = '5edd67050254abc33125ea1390b0cc6d83a5896a3ebf1e3ea72901198e734a51'
ACL_SHA = 'c73b4647cf99ab38a6dc9c00af5b9c40d8a71d7c77fc56ca0e70b61687052f77'
LIB_SHA = '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41'
AGS_SHA = '12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729'
BATTLE_GLB_SHA = 'd5b95640f8c721721bbbefb7590d97ab10631c32e5770e18b781462f728f7828'
SFX_SHA = '4be30fddd6c2e6c0d612e33e691ac018ca0bb37699c74a54484cd32cfe2c6f5d'
GIM_SHA = 'cec24d79e67c9bc86993d0ab4115f484d6e222f0954252d02d8505899d0eccf7'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_effect_binding(raw):
    """Keep the authored socket separate from skin joints and native enums."""
    if sha(raw) != GIM_SHA:
        raise ValueError('Original battle GIM identity changed')
    tree = ET.fromstring(raw.decode('gb18030'))
    triggers = tree.findall('./Triggers/fight_idle_show/event_1/trigger')
    if len(triggers) != 1:
        raise ValueError('Entrance cue must have exactly one source trigger')
    trigger = triggers[0]
    if (trigger.get('SocketName'), trigger.get('ObjectFileName')) != (
            'fx_center', 'effects/player/001/fight_idle_show_chuchang.sfx'):
        raise ValueError('Source entrance effect socket/binding changed')
    sockets = [s for s in tree.findall('./Sockets/*') if s.get('Name') == trigger.get('SocketName')]
    if len(sockets) != 1:
        raise ValueError('Entrance socket must be uniquely authored in GIM')
    socket = sockets[0]
    matrix = [float(v) for v in socket.attrib['MatrixToBone'].split(',')]
    if len(matrix) != 16 or not np.isfinite(matrix).all():
        raise ValueError('Invalid source socket matrix')
    bound = [dict(x.attrib) for x in socket.findall('./BoundObject/Object')]
    if sum(x.get('Name', '').replace('\\', '/') == trigger.get('ObjectFileName')
           and x.get('Active') == 'true' for x in bound) != 1:
        raise ValueError('Entrance SFX must be active on its authored socket')
    return {'schema': 'hczs-elsa-entrance-binding-v1', 'sourceGimSha256': GIM_SHA,
            'trigger': dict(trigger.attrib), 'socket': dict(socket.attrib),
            'socketXmlTag': socket.tag, 'boundObjects': bound, 'matrixLiteralValues': matrix,
            'boneNameAuthored': socket.get('BoneName'),
            'identityMatrixLiteral': matrix == [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.],
            'runtimeBindingVerified': False,
            'limitations': ['GIM socket is not a skin joint; missing BoneName must not select an arbitrary bone.',
                            'BindType=7 is retained literally; identity matrix alone does not establish native attachment semantics.']}


def check_battle_skeleton(base):
    """Verify identity against the GLB actually staged for the battle actor."""
    battle_path = ROOT / 'analysis/unreal/battle-inputs/player/elsa_battle.glb'
    battle_raw = battle_path.read_bytes()
    if sha(battle_raw) != BATTLE_GLB_SHA:
        raise ValueError('Existing battle import source changed; re-review its skeleton')
    doc, binary = split_glb(base)
    battle, battle_binary = split_glb(battle_raw)
    joints = doc['skins'][0]['joints']
    if doc['skins'] != battle['skins'] or len(joints) != 180:
        raise ValueError('File_26 and current battle skins/joint ordering differ')
    names = [doc['nodes'][i]['name'] for i in joints]
    for node in joints:
        if any(doc['nodes'][node].get(k) != battle['nodes'][node].get(k) for k in ('name', 'children')):
            raise ValueError('File_26 and current battle skeleton identity/hierarchy differ')
    ibm = doc['skins'][0]['inverseBindMatrices']
    if not np.array_equal(accessor_array(doc, binary, ibm), accessor_array(battle, battle_binary, ibm)):
        raise ValueError('File_26 and current battle inverse bind matrices differ')
    return names, {'stagedBattleGlb': str(battle_path.relative_to(ROOT)),
                   'stagedBattleGlbSha256': BATTLE_GLB_SHA, 'bones': len(names),
                   'jointOrderNamesHierarchyAndInverseBindsIdentical': True}


def main(out=OUT):
    out = Path(out).resolve()
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    library_path = ROOT / 'analysis/animation/recovered/ailisha.gisacl'
    event_path = ROOT / 'analysis/battle-visual/skill-animation/ailisha.ags'
    if file_sha256(apk) != APK_SHA256:
        raise ValueError('APK identity changed')
    if file_sha256(library_path) != LIB_SHA or file_sha256(event_path) != AGS_SHA:
        raise ValueError('Original animation library/event track changed')
    library = parse_library(library_path.read_bytes())
    base, mesh_sources, bind = build_source_base()
    names, skeleton_check = check_battle_skeleton(base)
    out.mkdir(parents=True, exist_ok=True)
    logical_path = clip_path('character/player/ailisha/ailisha.gisacl', NAME)
    source = extract_with_provenance(apk, read_catalogue(apk), logical_path,
                                     out / (NAME + '.gisacl'), APK_SHA256)
    parsed = parse_clip((out / (NAME + '.gisacl')).read_bytes())
    record = next(c for c in library['clips'] if c['name'] == NAME)
    if (parsed['sha256'], parsed['acl_sha256'], parsed['bone_count'], parsed['samples'],
            parsed['sample_rate'], parsed['duration_seconds']) != (CLIP_SHA, ACL_SHA, 180, 112, 30., 3.7):
        raise ValueError('Original entrance clip identity or timing changed')
    if record['duration_ms'] != 3700:
        raise ValueError('Library duration differs from sampled clip')
    parsed.update(source=source, library_sha256=LIB_SHA,
                  bone_mapping=map_bones(library, parsed, names), library_record=record)
    write_json(out / (NAME + '.json'), parsed)
    sample_pinned(out, {NAME: ACL_SHA}, 'elsa-entrance', 0)
    clip = load_clip(out, NAME, library, names)
    glb, animations, bind_error = encode(base, [clip])
    doc, binary = split_glb(glb)
    # Generic Elsa exporter annotates a different hall mesh; this is File_26.
    doc['extras'].pop('knownBindDifference', None)
    doc['extras']['scenePlaybackScope'] = 'Original fight_idle_show on File_26 battle skeleton; scene-independent clip only.'
    glb = pack_glb(doc, binary)
    validation = validate_roundtrip(base, glb, [clip])
    if validation[0]['moving_tracks'] == 0 or validation[0]['sample_count_verified'] != 20160:
        raise ValueError('Entrance motion/sample verification failed')
    track = ET.fromstring(event_path.read_bytes()).find('.//EventTrack_' + NAME)
    if track is None:
        raise ValueError('Missing source entrance event track')
    events = sorted([{'name': e.attrib['Name'], 'ratioLiteral': e.attrib['TimeRatio'],
                      'ratio': float(e.attrib['TimeRatio']),
                      'seconds': float(e.attrib['TimeRatio']) * 3.7}
                     for e in track.findall('Event')], key=lambda e: e['ratio'])
    cue = [e for e in events if e['name'] == 'event_1']
    if len(cue) != 1 or cue[0]['ratioLiteral'] != '0.144595':
        raise ValueError('Reviewed entrance effect cue changed')
    gim = ROOT / 'analysis/battle-visual/scene-export/source/File_26.gim'
    binding = source_effect_binding(gim.read_bytes())
    sfx = ROOT / 'analysis/battle-visual/prologue-theatre/source/3c076f28572afe506d4d.sfx'
    if file_sha256(sfx) != SFX_SHA:
        raise ValueError('Source entrance effect changed')
    cue[0]['trigger'] = binding['trigger']
    cue[0]['sourceBinding'] = binding
    cue[0]['sourceSfx'] = {'file': str(sfx.relative_to(ROOT)), 'sha256': SFX_SHA,
                         'playbackImplemented': False}
    target = out / 'elsa_entrance.glb'
    pending = target.with_suffix('.glb.pending')
    pending.write_bytes(glb)
    pending.replace(target)
    report = {'schema': 'hczs-elsa-entrance-animation-v1', 'originalApkExecuted': False,
              'source': source, 'librarySha256': LIB_SHA, 'eventTrackSha256': AGS_SHA,
              'meshSources': mesh_sources, 'bindValidation': bind, 'maxBindTrsError': bind_error,
              'battleSkeletonVerification': skeleton_check, 'boneNames': names,
              'animations': animations, 'verification': validation, 'events': events,
              'output': str(target), 'sha256': sha(glb),
              'limitations': ['Original samples verified offline; UE playback remains to verify.',
                             'glTF between-sample SLERP differs from ACL normalized LERP.',
                             'No map/camera/HUD/draw/SFX implementation or fabricated cube SHOW.',
                             '2133 prologue ruins, 2077 city and 2004 theatre remain distinct scenes.']}
    write_json(out / 'export-report.json', report)
    write_json(out / 'manifest.json', {'schemaVersion': 1, 'kind': 'hczs-battle-entrance',
        'file': target.name, 'sha256': sha(glb), 'report': 'export-report.json',
        'clip': NAME, 'durationSeconds': 3.7, 'sampleRate': 30, 'samples': 112,
        'boneCount': 180, 'loop': False, 'returnTo': 'idle_1',
        'event1': cue[0], 'events': events,
        'ueSkeleton': '/Game/Recovered/Battle/Elsa/elsa_battle_Skeleton.elsa_battle_Skeleton',
        'ueDestination': '/Game/Recovered/Battle/Entrance',
        'freshBattleOnly': True, 'replayOnResume': False,
        'sourcePlayerShow': {'delaySeconds': .5, 'visibleAfterShowSeconds': .01,
                            'otherPlayersVisibleAfterClip': True}})
    return {'output': str(target), 'sha256': sha(glb), 'duration': 3.7, 'bones': len(names),
            'sampledBoneFrames': validation[0]['sample_count_verified'],
            'movingTracks': validation[0]['moving_tracks'], 'event1Seconds': cue[0]['seconds']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--inspect-binding', action='store_true', help='Inspect the pinned GIM socket without resampling or asset mutation')
    args = parser.parse_args()
    result = source_effect_binding((ROOT/'analysis/battle-visual/scene-export/source/File_26.gim').read_bytes()) if args.inspect_binding else main(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
