"""Join original animation cues, event timing, media and gain without inventing aliases."""
import json
import xml.etree.ElementTree as ET

from extract_npk import ROOT
from inspect_enemy_audio import sha
from trace_animation_audio import trace


def main():
    source = ROOT/'analysis/battle-visual/elsa-audio'
    cues = trace(source/'ailisha_music.ags',
                 '90287a47b0b2cfa55e866d539fa8016e9953e6c1119b84e5cb5f9a513984ec8a')['cues']
    routes = json.loads((source/'voice-routes.json').read_text('utf8'))
    mixes = json.loads((source/'voice-mix-ancestry.json').read_text('utf8'))['chains']
    decoded = json.loads((source/'voice-decode-report.json').read_text('utf8'))
    if decoded['source_report_sha256'] != sha((source/'voice-routes.json').read_bytes()):
        raise ValueError('voice decode provenance is stale; rerun --voice')
    media = {r['id']:r for r in decoded['media']}
    metadata = ROOT/'analysis/battle-visual/enemy-audio/SoundbanksInfo.xml'
    bank = [b for b in ET.parse(metadata).findall('.//SoundBank') if b.findtext('ShortName')=='ailisha_voice']
    if len(bank)!=1:
        raise ValueError('voice metadata bank not unique')
    by_id = {r['id']:r for r in routes['events']}
    names = {e.get('Name'):int(e.get('Id')) for e in bank[0].findall('IncludedEvents/Event')}
    rows, unresolved = [], []
    for cue in cues:
        if cue['clip'] not in ('fire_1','fire_1_1','fire_1_3','crit_1','death') or cue['cue']!='vo':
            continue
        if cue['bank_reference']!='wwise/ailisha_voice.bnk:ailisha_voice' or names.get(cue['event']) not in by_id:
            unresolved.append(dict(cue=cue,reason='Exact bank/event route unavailable; no alias substituted'))
            continue
        event = by_id[names[cue['event']]]
        stops = [a for a in event['actions'] if a['node_class']=='CAkActionStop']
        plays = [a for a in event['actions'] if a['node_class']=='CAkActionPlay' and 'status' not in a['target']]
        if len(stops)!=1 or len(plays)!=1:
            raise ValueError('unexpected event route')
        stop, play = stops[0], plays[0]
        group = int(stop['reference']['value'])
        def timing(action, prop):
            matches = [p for p in action['timing_properties'] if int(p['id']['value'])==prop]
            if len(matches)!=1:
                raise ValueError('ambiguous action timing')
            return matches[0]['milliseconds']
        target = play['target']
        sounds = [p['target'] for p in target['playlist']] if 'playlist' in target else [target]
        variants = []
        for sound in sounds:
            chain = mixes[str(sound['id'])]
            if group not in [n['id'] for n in chain]:
                raise ValueError('stop target does not contain voice')
            gain = sum(float(v['value']) for n in chain for p in n['properties']
                       if int(p['id']['value'])==0 for v in p['values']
                       if v['name']=='pValue' and v.get('float_verified'))
            item = media[sound['media_id']]
            pcm = source/'voice-pcm'/f"{sound['media_id']}.wav"
            if sha(pcm.read_bytes())!=item['pcm_sha256']:
                raise ValueError('voice PCM changed')
            variants.append(dict(sound_id=sound['id'],media=item,static_gain_db=gain,
                                 static_linear_gain=10**(gain/20),
                                 ancestry=[n['id'] for n in chain],
                                 rtpc_nodes=sorted({n['id'] for n in chain if n['rtpc_objects']})))
        rows.append(dict(cue=cue,event_id=event['id'],container_id=target['id'],
                         selection='source-sequence' if 'playlist' in target else 'single',
                         sequence_flags=target.get('sequence_flags'),
                         stop_group=group,stop_transition_ms=timing(stop,16),
                         play_delay_ms=timing(play,15),variants=variants,
                         unresolved_actions=[a['id'] for a in event['actions'] if 'status' in a['target']]))
    report = dict(evidence_kind='ordinary-local-static-tool',cues=rows,unresolved_cues=unresolved,
                  inputs={n:sha((source/n).read_bytes()) for n in
                          ('voice-routes.json','voice-mix-ancestry.json','voice-decode-report.json')},
                  metadata_sha256=sha(metadata.read_bytes()),
                  limitations=['Not client integration or original-runtime evidence.',
                               'Delay is additional to animation TimeRatio, not an absolute animation time.',
                               'Stop scope contains recovered sounds; external targets and runtime scope remain incomplete.',
                               'Static gain omits RTPC, high-pass filters, buses and effects; do not clamp positive dB silently.',
                               'Sequence reset/stop behavior requires runtime implementation and verification.'])
    (source/'battle-voice-cues.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(resolved_cues=len(rows),unresolved_cues=len(unresolved),
                          variants=sum(len(r['variants']) for r in rows))))


if __name__=='__main__':
    main()
