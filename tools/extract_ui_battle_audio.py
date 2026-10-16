"""Extract and verify the battle deal UI sounds (UI_DRAWCARD, UI_FAPAI_B) from ui_battle.bnk.

Run with the pinned wwiser XML export of the extracted bank:
  python .tools/wwiser/wwiser.py -d xml -dn analysis/battle-ui/audio/wwiser-ui-battle.xml analysis/battle-ui/audio/ui_battle.bnk
"""
import argparse
import array
import hashlib
import json
import re
import struct
import subprocess
import wave
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import chunks, sha

MEMBER = 'assets/res/wwise/ui_battle.bnk'
EVENTS = {'UI_DRAWCARD': 'ui_battle_fapai_a', 'UI_FAPAI_B': 'ui_battle_fapai_b'}
TABLE_LINES = {'UI_DRAWCARD': 436, 'UI_FAPAI_B': 451}
WWISER_COMMIT = '94580dd3de3280933d69c435e96d4e2c3b443207'
DECODER_ZIP_SHA = '6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c'
OUT = ROOT/'analysis/battle-ui/audio'


def verify_table():
    table = json.loads((ROOT/'analysis/battle-rules/03873_common__cdata__audio_event_table.py.json').read_text('utf8'))
    consts = [(i['source_line'], i.get('operand')) for i in table['code_objects'][0]['instructions'] if i['opname'] == 'LOAD_CONST']
    for key, event in EVENTS.items():
        line = TABLE_LINES[key]
        values = [v for l, v in consts if l == line]
        if values != ['ui/Event|'+event, 'ClipPath', key]:
            raise ValueError('audio_event_table entry changed: '+key)


def verify_decoder():
    tool_dir = ROOT/'.tools/vgmstream-r2117'
    release = ROOT/'.tools/vgmstream-r2117-win64.zip'
    if sha(release.read_bytes()) != DECODER_ZIP_SHA:
        raise ValueError('decoder release identity changed')
    with zipfile.ZipFile(release) as archive:
        for name in archive.namelist():
            if name.endswith(('.exe', '.dll')) and (tool_dir/name).read_bytes() != archive.read(name):
                raise ValueError('decoder executable/library changed')
    return tool_dir/'vgmstream-cli.exe'


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    verify_table()
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    metadata = ROOT/'analysis/battle-visual/enemy-audio/SoundbanksInfo.xml'
    if sha(metadata.read_bytes()) != 'b678fee4ae4f4e4e16e0bc71eadc2af37ae6bc980a6b73dc1117a674d1b483f2':
        raise ValueError('metadata identity changed')
    info = next(b for b in ET.parse(metadata).findall('.//SoundBank') if b.findtext('ShortName') == 'ui_battle')
    declared = {e.get('Name'): int(e.get('Id')) for e in info.findall('IncludedEvents/Event')}
    with zipfile.ZipFile(APK) as archive:
        raw = archive.read(MEMBER)
    OUT.mkdir(parents=True, exist_ok=True)
    bank_path = OUT/'ui_battle.bnk'
    if not bank_path.exists() or bank_path.read_bytes() != raw:
        bank_path.write_bytes(raw)
    parts = chunks(raw)
    version, ident = struct.unpack_from('<II', parts[b'BKHD'][1])
    if version != 120 or ident != int(info.get('Id')):
        raise ValueError('bank metadata mismatch')
    data_offset, data = parts[b'DATA']
    media = {}
    for media_id, offset, size in struct.iter_unpack('<III', parts[b'DIDX'][1]):
        if offset+size > len(data) or media_id in media:
            raise ValueError('media range/identity mismatch')
        media[media_id] = (data_offset+offset, data[offset:offset+size])

    commit = subprocess.check_output(['git', '-C', str(ROOT/'.tools/wwiser'), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != WWISER_COMMIT:
        raise ValueError('wwiser version changed')
    xml = OUT/'wwiser-ui-battle.xml'
    records = {}
    for node in ET.parse(xml).getroot().iter('object'):
        found = node.find("field[@name='ulID']")
        if found is not None:
            key = int(found.get('value'))
            if key in records:
                raise ValueError('duplicate object ID')
            records[key] = node

    def own_fields(node, name):
        return [f for f in node.iter('field') if f.get('name') == name]

    def field(node, name):
        found = own_fields(node, name)
        if len(found) != 1:
            raise ValueError('field not unique: '+name)
        f = found[0]
        offset, value = int(f.get('offset')), f.get('value')
        kind = f.get('type')
        if kind == 'f32':
            if abs(struct.unpack_from('<f', raw, offset)[0]-float(value)) > 1e-4:
                raise ValueError('XML float disagrees with bytes')
            return float(value)
        code = {'u8': 'B', 'u16': 'H', 'u32': 'I', 'sid': 'I', 'tid': 'I'}[kind]
        if struct.unpack_from('<'+code, raw, offset)[0] != int(value):
            raise ValueError('XML field disagrees with bytes: '+name)
        return int(value)

    def props(node):
        """Initial-value property bundle (pID/pValue pairs) owned directly by this object."""
        out = {}
        for bundle in node.iter('list'):
            if bundle.get('name') != 'pProps':
                continue
            for prop in bundle.findall('object'):
                pid, value = prop.find("field[@name='pID']"), prop.find("field[@name='pValue']")
                out[pid.get('valuefmt', pid.get('value')).split('[')[-1].rstrip(']')] = float(value.get('value'))
        return out

    def parent_chain(node_id):
        chain, current = [], node_id
        while current and current in records:
            node = records[current]
            chain.append(dict(id=current, cls=node.get('name'), props=props(node)))
            parent = own_fields(node, 'DirectParentID')
            current = int(parent[0].get('value')) if parent else 0
        return chain, current

    def sound(node_id):
        node = records[node_id]
        if node.get('name') != 'CAkSound':
            raise ValueError('expected sound')
        plugin, stream_type = field(node, 'ulPluginID'), field(node, 'StreamType')
        source_id, size = field(node, 'sourceID'), field(node, 'uInMemoryMediaSize')
        if stream_type != 0 or source_id not in media or len(media[source_id][1]) != size:
            raise ValueError('sound media is not in-bank as declared')
        chain, outside = parent_chain(node_id)
        volume = sum(c['props'].get('Volume', 0.0) for c in chain)
        return dict(id=node_id, plugin=plugin, source_id=source_id, bytes=size, chain=chain,
                    first_parent_outside_bank=outside, hierarchy_volume_db=volume)

    routes = {}
    used = set()
    for key, name in EVENTS.items():
        event = records[declared[name]]
        if event.get('name') != 'CAkEvent':
            raise ValueError('declared event not parsed as event')
        actions = []
        for ref in own_fields(event, 'ulActionID'):
            action_id = int(ref.get('value'))
            if struct.unpack_from('<I', raw, int(ref.get('offset')))[0] != action_id:
                raise ValueError('action reference mismatch')
            action = records[action_id]
            target_id = field(action, 'idExt')
            row = dict(id=action_id, cls=action.get('name'), action_type=field(action, 'ulActionType'),
                       target=target_id, props=props(action))
            target = records[target_id]
            if action.get('name') == 'CAkActionPlay':
                if target.get('name') == 'CAkRanSeqCntr':
                    if field(target, 'eRandomMode') != 0:
                        raise ValueError('unexpected random mode')
                    row['container'] = dict(id=target_id, mode='random', props=props(target),
                                            avoid_repeat=field(target, 'wAvoidRepeatCount'),
                                            loop_count=field(target, 'sLoopCount'),
                                            children=[sound(int(c.get('value'))) for c in own_fields(target, 'ulChildID')])
                    row['sounds'] = row['container']['children']
                else:
                    row['sounds'] = [sound(target_id)]
                used.update(s['source_id'] for s in row['sounds'])
            else:
                row['target_class'] = target.get('name')
            actions.append(row)
        routes[key] = dict(event=name, event_id=declared[name], actions=actions)

    decoder = verify_decoder()
    pcm_dir = OUT/'pcm'
    pcm_dir.mkdir(exist_ok=True)
    decoded = {}
    for source_id in sorted(used):
        offset, payload = media[source_id]
        if payload[:4] != b'RIFF' or payload[8:12] != b'WAVE' or struct.unpack_from('<I', payload, 4)[0]+8 != len(payload):
            raise ValueError('unexpected media header')
        original = OUT/f'{source_id}.wem'
        original.write_bytes(payload)
        destination = pcm_dir/f'{source_id}.wav'
        result = subprocess.run([str(decoder), '-i', '-o', str(destination), str(original)],
                                capture_output=True, text=True, check=True)
        samples = re.search(r'stream total samples: (\d+)', result.stdout)
        with wave.open(str(destination), 'rb') as wav:
            frames, rate, channels, width = wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            pcm = array.array('h', wav.readframes(frames))
        if not samples or frames != int(samples[1]) or width != 2 or not any(pcm):
            raise ValueError('decode mismatch or silent output')
        decoded[source_id] = dict(bank_offset=offset, wem_sha256=sha(payload), pcm_sha256=sha(destination.read_bytes()),
                                  frames=frames, sample_rate=rate, channels=channels,
                                  duration_seconds=frames/rate, peak=max(abs(v) for v in pcm))
    report = dict(evidence_kind='ordinary-local-static-tool', apk_sha256=APK_SHA256, member=MEMBER, bank_sha256=sha(raw),
                  wwiser_commit=commit, xml_sha256=sha(xml.read_bytes()), decoder_sha256=sha(decoder.read_bytes()),
                  routes=routes, media=decoded,
                  limitations=['Bus volumes, LPF/HPF, voice limits and the master mix live outside this bank and are not reproduced.',
                               'Random container choice is approximated by uniform selection with the recorded avoid-repeat count.',
                               'Stop actions are recorded; they only matter if their target sound is playing.',
                               'Ordinary local static evidence, not original-client runtime evidence.'])
    (OUT/'fapai-routes.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: [(a['cls'], [(s['source_id'], round(s['hierarchy_volume_db'], 2)) for s in a.get('sounds', [])])
                          for a in v['actions']] for k, v in routes.items()}))
    print(json.dumps({k: round(v['duration_seconds'], 3) for k, v in decoded.items()}))


if __name__ == '__main__':
    main()
