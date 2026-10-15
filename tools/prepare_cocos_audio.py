"""Stage proven source cues; preserve incomplete mixing as an explicit limitation."""
import json
import shutil
from extract_npk import ROOT
from inspect_enemy_audio import sha


def main():
    source = ROOT/'analysis/battle-visual/elsa-audio'
    cues = json.loads((source/'animation-cues.json').read_text('utf8'))['elsa']['cues']
    mixes = json.loads((source/'mix-ancestry.json').read_text('utf8'))['chains']
    decoded = {r['id']:r for r in json.loads((source/'decode-report.json').read_text('utf8'))['media']}
    out = ROOT/'legacy/cocos-poc/assets/resources/recovered/audio'
    out.mkdir(parents=True,exist_ok=True)
    rows = []
    for cue in cues:
        if cue['clip'] not in ('crit_1','fire_1_1','fire_1_3','death') or cue['cue']!='sound':
            continue
        route = cue['verified_bank_route']
        if cue['route_status']!='resolved' or len(route['actions'])!=1:
            raise ValueError('ambiguous audio route')
        action = route['actions'][0]
        media = action['media']
        ident = next(f['value'] for f in action['fields'] if f['name']=='idExt')
        volume = 0.0
        for node in mixes[str(ident)]:
            for prop in node['properties']:
                if int(prop['id']['value'])==0:
                    for v in prop['values']:
                        if v['name']=='pValue' and v.get('float_verified'):
                            volume += float(v['value'])
        pcm = source/'pcm'/f"{media['id']}.wav"
        if sha(pcm.read_bytes()) != decoded[media['id']]['pcm_sha256']:
            raise ValueError('PCM identity mismatch')
        shutil.copyfile(pcm,out/pcm.name)
        rows.append(dict(clip=cue['clip'],ratio=cue['time_ratio'],event=cue['event'],
                         resource=f"recovered/audio/{media['id']}",volume=10**(volume/20),
                         static_volume_db=volume,pcm_sha256=sha(pcm.read_bytes())))
    if len(rows)!=4:
        raise ValueError('expected four proven cues')
    voice = json.loads((source/'battle-voice-cues.json').read_text('utf8'))
    for name, digest in voice['inputs'].items():
        if sha((source/name).read_bytes()) != digest:
            raise ValueError('voice evidence changed: '+name)
    for row in voice['cues']:
        variants=[]
        for variant in row['variants']:
            media=variant['media']; pcm=source/'voice-pcm'/f"{media['id']}.wav"
            if sha(pcm.read_bytes())!=media['pcm_sha256']:
                raise ValueError('voice PCM changed')
            shutil.copyfile(pcm,out/pcm.name)
            variants.append(dict(resource=f"recovered/audio/{media['id']}",
                                 volume=variant['static_linear_gain'],pcm_sha256=media['pcm_sha256'],
                                 sound_id=variant['sound_id'],static_volume_db=variant['static_gain_db']))
        rows.append(dict(clip=row['cue']['clip'],ratio=row['cue']['time_ratio'],event=row['cue']['event'],
                         variants=variants,sequence=str(row['container_id']),group=str(row['stop_group']),
                         delay=row['play_delay_ms']/1000,fade=row['stop_transition_ms']/1000))
    # Explicit preview master gives positive authored gains room in AudioSource's [0,1] range.
    master=0.8
    if any(v['volume']*master>1 for c in rows for v in c.get('variants',[c])):
        raise ValueError('master headroom insufficient; do not silently clamp')
    (out/'cues.json').write_text(json.dumps(dict(cues=rows,master_volume=master, limitations=[
        'Source media and TimeRatio; static actor ancestry gain only.',
        'Preview master 0.8 is a reconstruction policy, not the original bus gain.',
        'Voice sequences advance per active battle audio instance; original global lifetime unverified.',
        'Original buses, HPF, RTPC, effects and external voice Play targets remain incomplete.',
        'fire_1 SFX / fire_1_1 voice legacy bank aliases and enemy audio remain unresolved.']),indent=2),encoding='utf8')
    print(json.dumps(dict(cues=len(rows),master_volume=master)))


if __name__=='__main__':
    main()
