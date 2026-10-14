"""Preserve native trigger-to-event population evidence without running the APK."""
import hashlib
import json
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from trace_native_target_arrow import SOURCE, EXPECTED, OBJDUMP
from inspect_neox_animation import parse_library, parse_clip

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/enemy-timing'


def main():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Native source changed')
    u32 = lambda at: struct.unpack_from('<I', data, at)[0]
    ph = u32(28)
    stride, count = struct.unpack_from('<HH', data, 42)
    loads = [struct.unpack_from('<8I', data, ph + i * stride) for i in range(count)]

    def offset(va):
        for kind, at, start, _, length, *_ in loads:
            if kind == 1 and start <= va < start + length:
                return at + va - start
        raise ValueError(f'Unmapped VA {va:#x}')

    def string(va):
        at = offset(va)
        return data[at:data.index(b'\0', at)].decode('ascii')

    anchors = []
    for va, expected in [(0x95d794, 'AnimationEventTracks'), (0x95e430, 'TimeRatio'),
                         (0x9963f0, 'Version'), (0xaef510, 'Time'),
                         ((u32(offset(0x996464)) + 0x995ca4) & 0xffffffff, 'AnimationEventTracks'),
                         ((u32(offset(0xaef5b4)) + 0xaef1f2) & 0xffffffff, 'TimeRatio'),
                         ((u32(offset(0xaef57c)) + 0xaef222) & 0xffffffff, 'Name'),
                         ((u32(offset(0x95e420)) + 0x95de7a) & 0xffffffff, 'Triggers')]:
        if string(va) != expected:
            raise ValueError('Property string anchor changed')
        anchors.append(dict(va=hex(va), value=expected))
    table = 0x2982d00
    rtti = u32(offset(table) - 4)
    type_name = string(u32(offset(rtti) + 4))
    if (type_name != 'N4neox5world16MeshSkeletalDataE'
            or u32(offset(table) + 0xe8) != 0x95d7b1
            or u32(offset(table) + 0xec) != 0x95dd3d
            or u32(offset(0x2984d88) + 0x44) != 0x996da7):
        raise ValueError('MeshSkeletalData table changed')

    # Constructor 0xaee550 installs the literal-relative table plus its ABI header.
    event_table = (u32(offset(0xaee578)) + 0xaee562 + 8) & 0xffffffff
    event_rtti = u32(offset(event_table) - 4)
    event_type = string(u32(offset(event_rtti) + 4))
    event_slots = {hex(slot): hex(u32(offset(event_table) + slot)) for slot in [0, 0x1c, 0x44]}
    if (event_type != 'N4neox5world20AnimTriggerContainerE'
            or event_slots != {'0x0': '0xaf0251', '0x1c': '0xaf0399', '0x44': '0xaee57d'}):
        raise ValueError('Concrete event container changed')
    default_table = (u32(offset(0xaef8d8)) + 0xaef83a + 8) & 0xffffffff
    if default_table != event_table:
        raise ValueError('Default event constructor table changed')

    exports = []
    for name, start, end in [('event-track-dispatch', 0x95d6e6, 0x95d7b0),
                             ('event-track-loader', 0x95d7b0, 0x95dd3c),
                             ('music-trigger-loader', 0x95dd3c, 0x95e4d0),
                             ('event-record-lookup-insert', 0x997020, 0x997102),
                             ('skel-animation-scalar', 0x996da6, 0x996dbe),
                             ('skel-event-xml-dispatch', 0x995c94, 0x995da8),
                             ('event-container-constructor', 0xaee550, 0xaee59c),
                             ('event-container-xml', 0xaef030, 0xaef5bc),
                             ('event-container-insert-count', 0xaf0250, 0xaf03b8),
                             ('default-event-install', 0x994112, 0x99414e),
                             ('default-start-end-events', 0xaef810, 0xaef8e0),
                             ('animation-record-reader', 0x990128, 0x9901ea),
                             ('animation-record-dispatch', 0x994544, 0x994578),
                             ('acl-duration-init', 0x98d908, 0x98da4c)]:
        command = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
                   f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        output = subprocess.run(command, capture_output=True, check=True).stdout
        path = OUT / (name + '.thumb.txt')
        path.write_bytes(output)
        exports.append(dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(output).hexdigest(), command=command))

    music_path = ROOT / 'analysis/battle-visual/enemy-skills/enemy-music.ags'
    provenance = json.loads(music_path.with_name('enemy-music.source.json').read_text('utf8'))
    music = music_path.read_bytes()
    if hashlib.sha256(music).hexdigest() != provenance['sha256']:
        raise ValueError('Cube music source changed')
    triggers = ET.fromstring(music).find('Triggers')
    events = {clip.tag: [dict(name=e.tag, attributes=e.attrib,
                            actions=[a.attrib for a in e]) for e in clip] for clip in triggers}
    attack_names = [dict(clip=clip, event=e) for clip, entries in events.items()
                    for e in entries if e['name'] == 'attack' or e['name'].startswith('attack_')]
    library_path = ROOT / 'analysis/first-encounter/enemy-model.gisacl'
    library_data = library_path.read_bytes()
    if hashlib.sha256(library_data).hexdigest() != 'cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0':
        raise ValueError('Cube library changed')
    library = parse_library(library_data)
    comparisons = []
    for name, directory in [('fire', 'tutorial-enemy-animation'), ('idle', 'tutorial-enemy-animation'),
                            ('skill_2', 'battle-visual/enemy-skills'), ('skill_3', 'battle-visual/enemy-skills')]:
        clip_path = ROOT / 'analysis' / directory / (name + '.gisacl')
        clip = parse_clip(clip_path.read_bytes())
        source = json.loads(clip_path.with_suffix('.gisacl.source.json').read_text('utf8'))
        if source['sha256'] != clip['sha256']:
            raise ValueError('Cube clip identity changed')
        record = next(c for c in library['clips'] if c['name'] == name)
        # Independent ACL header duration compared to the authored RGIS record.
        error = abs(record['duration_ms'] - clip['duration_seconds'] * 1000)
        if error > 0.001:
            raise ValueError('Record and ACL durations disagree')
        comparisons.append(dict(name=name, record_ms=record['duration_ms'],
                                acl_seconds=clip['duration_seconds'], error_ms=error,
                                clip_sha256=clip['sha256']))
    report = dict(
        evidence_kind='Local static ELF/LLVM and source XML; not REA/runtime observation',
        native_sha256=EXPECTED, anchors=anchors,
        event_track_loader=dict(type_name=type_name, vtable_va=hex(table), slot='0xe8', pointer='0x95d7b1',
                                music_slot='0xec', music_pointer='0x95dd3d'),
        event_container=dict(type_name=event_type, vtable_va=hex(event_table), slots=event_slots,
                             constructor='0xaee550', xml_reader='0xaef030'),
        cube_library=dict(sha256=library['sha256'], clips=library['clips'], acl_comparisons=comparisons),
        exports=exports, cube_music=dict(provenance=provenance, events=events, attack_named_events=attack_names),
        observations=[
            '0x95d6f0 references AnimationEventTracks and dispatches through MeshSkeletalData slot +0xe8 to 0x95d7b0.',
            'A separate function starts at 0x95dd3c. At 0x95de76 it resolves Triggers from the object+0x720 resource.',
            '0x95e294 references TimeRatio; the float property reader receives sp+0x3c as output and -1.0 as default.',
            'The branch at 0x95e2b6 reaches 0x95e1aa only when the object+0x754 string-length condition is zero.',
            'That branch resolves an animation through vtable+0x28 and rejects ID 0xffff; 0x997020 looks up an event by name in the same +0x94 / +8 arrays as the query accessor.',
            'For TimeRatio > -1, 0x95e1e8 calls animation-container vtable+0x44. Its float result is multiplied by TimeRatio at 0x95e1f6.',
            'Existing event+0 is overwritten at 0x95e1fc; a missing event is passed to 0x9970ee, which dispatches to the selected animation event object vtable slot zero.',
            'SkelAnimsData slot +0x44 points to 0x996da6, which reads selected animation+0x48c. The fixed-record assignment and unit corroboration are described below.',
            'SkelAnimsData XML path at 0x995c94 resolves AnimationEventTracks, reads Version with default 1 into container+0xa0, then iterates tracks.',
            'The XML track name buffer is addressed at +11 before animation-name resolution. The observed EventTrack_ prefix is 11 bytes; this is suffix extraction, not evidence of prefix validation.',
            '0x995d54 selects animation+0x48c, allocates 0x24 bytes, constructs AnimTriggerContainer, installs it in the +0x94 vector, and calls 0xaef030 with the XML track and version.',
            'Constructor 0xaee550 stores the supplied float at object+4 and initializes empty event vectors. RTTI identifies AnimTriggerContainer.',
            'For non-Morph XML children, 0xaef108 selects Time for unsigned version <=1; otherwise 0xaef1dc reads TimeRatio and multiplies by object+4 at 0xaef1fa.',
            'The XML reader writes the computed float to event+0 at 0xaef208 and copies the Name property to event+4 at 0xaef222..0xaef22a.',
            'The concrete insertion slot is 0xaf0250; it searches by float time and handles insertion, equal-time name update and empty-name deletion. Thus it must not be modeled as an unconditional append.',
            'Concrete count slot 0xaf0398 returns (event_vector_end-event_vector_begin)/4, closing the previously unresolved count dispatch.',
            'Reader 0x990128 copies fixed RGIS record+0x44c to BonesAnimData+0x48c without conversion, and advances by record size 0x454 (1108).',
            'Four source-bound cube clips independently match RGIS duration /1000 to ACL (samples-1)/sample_rate within 0.001 milliseconds; this supports milliseconds for the authored field.',
            'The ACL initialization path 0x98d9b8..0x98d9e8 independently calculates float32 (sample_count-1)/sample_rate and stores it in the decompression context+24. This is a different field from BonesAnimData+0x48c.',
            '0x994112..0x994148 fills only null animation-event slots via 0xaef810, passing animation+0x48c. That factory creates start at 0 and end at the supplied value, with no attack event.',
        ],
        limitations=[
            'The complete loader call order, condition at object+0x754 and actual final cube event cache remain unresolved.',
            'The four-clip unit check is source-bound static corroboration, not original wall-clock playback. Alternate loaders can overwrite animation+0x48c.',
            'The fixed library record still has opaque fields; complete byte coverage does not prove their semantics or absence of other event sources.',
            'The cube music XML contains sound/voice triggers; these must not be used as damage timing simply because they have TimeRatio.',
            'No original runtime observation establishes the final cube event cache or excludes other event sources.',
            'No client hit-time change is justified by this report alone.',
        ])
    path = OUT / 'loader-chain.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(exports=len(exports), cube_clips=list(events), attack_named_events=len(attack_names))))


if __name__ == '__main__':
    main()
