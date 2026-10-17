"""Decode Future skill-bank cues used by the prologue ally clips.

MusicTriggers in future_music.ags name these events. Only a direct play action
onto one in-bank sound is decoded. Container, voice and bus volumes stay out.
"""
import argparse
import array
import hashlib
import json
import re
import struct
import subprocess
import sys
import wave
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import chunks, sha

sys.path.insert(0, str(ROOT/'.tools/wwiser'))
from wwiser.wfnv import Fnv

MEMBER = 'assets/res/wwise/future_skill.bnk'
BANK_SHA = 'ab9fe8c22008708497a2093b5fe56600b7c8e6dc514e27c9fa6e75a8318cdcd8'
MUSIC_SHA = '689c644d397f73c390a0b0806faddd5f10a229a6d3ea42536331593c22a3783b'
WWISER_COMMIT = '94580dd3de3280933d69c435e96d4e2c3b443207'
DECODER_ZIP_SHA = '6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c'
OUT = ROOT/'analysis/characters/hero-003/battle-actions/source'
CUES = {
    'show': dict(cue='sound2', ratio=0.0235, event='future_show_2'),
    'shield_1': dict(cue='sound2', ratio=0.0105, event='future_shield1'),
    'buff_2': dict(cue='sound', ratio=0.0148, event='future_buff2'),
}


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
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    with zipfile.ZipFile(APK) as archive:
        raw = archive.read(MEMBER)
    if sha(raw) != BANK_SHA:
        raise ValueError('future_skill.bnk identity changed')
    music = OUT/'future_music.ags'
    if sha(music.read_bytes()) != MUSIC_SHA:
        raise ValueError('future_music.ags identity changed')
    from trace_animation_audio import trace
    cues = trace(music, MUSIC_SHA)['cues']
    for clip, spec in CUES.items():
        matched = [c for c in cues if c['clip'] == clip and c['cue'] == spec['cue']
                   and c['time_ratio'] == spec['ratio'] and c['event'] == spec['event']]
        if len(matched) != 1:
            raise ValueError('music cue changed: '+clip)
    parts = chunks(raw)
    version, ident = struct.unpack_from('<II', parts[b'BKHD'][1])
    if version != 120 or ident != Fnv().get_hash('future_skill'):
        raise ValueError('bank header mismatch')
    data_offset, data = parts[b'DATA']
    media = {}
    for media_id, offset, size in struct.iter_unpack('<III', parts[b'DIDX'][1]):
        if offset+size > len(data) or media_id in media:
            raise ValueError('media range/identity mismatch')
        media[media_id] = (data_offset+offset, data[offset:offset+size])
    commit = subprocess.check_output(['git', '-C', str(ROOT/'.tools/wwiser'), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != WWISER_COMMIT:
        raise ValueError('wwiser version changed')
    xml = OUT/'future_skill.xml'
    records = {}
    for node in ET.parse(xml).getroot().iter('object'):
        found = node.find("field[@name='ulID']")
        if found is None:
            continue
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
        item = found[0]
        offset, value = int(item.get('offset')), item.get('value')
        kind = item.get('type')
        if kind == 'f32':
            if abs(struct.unpack_from('<f', raw, offset)[0]-float(value)) > 1e-4:
                raise ValueError('XML float disagrees with bytes')
            return float(value)
        code = {'u8': 'B', 'u16': 'H', 'u32': 'I', 'sid': 'I', 'tid': 'I'}[kind]
        if struct.unpack_from('<'+code, raw, offset)[0] != int(value):
            raise ValueError('XML field disagrees with bytes: '+name)
        return int(value)

    def props(node):
        out = {}
        for bundle in node.iter('list'):
            if bundle.get('name') != 'pProps':
                continue
            for prop in bundle.findall('object'):
                pid, value = prop.find("field[@name='pID']"), prop.find("field[@name='pValue']")
                out[pid.get('valuefmt', pid.get('value')).split('[')[-1].rstrip(']')] = float(value.get('value'))
        return out

    def parent_chain(node_id):
        chain, current, seen = [], node_id, set()
        while current and current in records and current not in seen:
            seen.add(current)
            node = records[current]
            chain.append(dict(id=current, cls=node.get('name'), props=props(node)))
            parent = [f for f in node.iter('field') if f.get('name') == 'DirectParentID']
            if len(parent) != 1:
                raise ValueError('parent field is not unique')
            current = int(parent[0].get('value'))
        return chain

    def sound(node_id):
        node = records[node_id]
        if node.get('name') != 'CAkSound':
            raise ValueError('expected one sound, got '+node.get('name'))
        if field(node, 'StreamType') != 0:
            raise ValueError('sound is not in-bank')
        source_id, size = field(node, 'sourceID'), field(node, 'uInMemoryMediaSize')
        if source_id not in media or len(media[source_id][1]) != size:
            raise ValueError('sound media is not in-bank as declared')
        chain = parent_chain(node_id)
        volume = sum(item['props'].get('Volume', 0.0) for item in chain)
        return dict(id=node_id, source_id=source_id, bytes=size, chain=chain, hierarchy_volume_db=volume)

    decoder = verify_decoder()
    pcm_dir = OUT/'pcm'
    pcm_dir.mkdir(exist_ok=True)
    rows = {}
    for clip, spec in CUES.items():
        event_id = Fnv().get_hash(spec['event'])
        event = records[event_id]
        if event.get('name') != 'CAkEvent':
            raise ValueError('hashed name is not an event')
        actions = []
        seen = []
        for ref in [f for f in event.iter('field') if f.get('name') == 'ulActionID']:
            action_id = int(ref.get('value'))
            action = records[action_id]
            action_type = field(action, 'ulActionType')
            seen.append(action.get('name')+':'+str(action_type))
            if action.get('name') != 'CAkActionPlay':
                continue
            target_id = field(action, 'idExt')
            actions.append(sound(target_id))
        if len(actions) != 1:
            raise ValueError('expected one play target for %s: %s' % (spec['event'], ','.join(seen)))
        row = actions[0]
        source_id = row['source_id']
        payload = media[source_id][1]
        wem = OUT/f'{source_id}.wem'
        wem.write_bytes(payload)
        destination = pcm_dir/f'{source_id}.wav'
        result = subprocess.run([str(decoder), '-i', '-o', str(destination), str(wem)],
                                capture_output=True, text=True, check=True)
        samples = re.search(r'stream total samples: (\d+)', result.stdout)
        with wave.open(str(destination), 'rb') as wav:
            frames, rate, channels, width = wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            pcm = array.array('h', wav.readframes(frames))
        if not samples or frames != int(samples[1]) or width != 2 or not any(pcm):
            raise ValueError('decode mismatch or silent output')
        row.update(spec, event_id=event_id, wem_sha256=sha(payload), pcm_sha256=sha(destination.read_bytes()),
                   frames=frames, sample_rate=rate, channels=channels, duration_seconds=frames/rate)
        rows[clip] = row
    report = dict(bank_sha256=BANK_SHA, music_sha256=MUSIC_SHA, wwiser_commit=commit,
                  cues=rows,
                  limitations=['Bus and master volumes are outside this bank and are not applied.',
                               'Voice events and the shield ailisha_skill copy are not played.',
                               'Ordinary local static evidence, not original-client runtime evidence.'])
    (OUT/'future-skill-audio.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({clip: dict(event=row['event'], source=row['source_id'], db=round(row['hierarchy_volume_db'], 3),
                                 seconds=round(row['duration_seconds'], 3), pcm=row['pcm_sha256'])
                      for clip, row in rows.items()}, indent=2))


if __name__ == '__main__':
    main()
