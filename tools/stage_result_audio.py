"""Stage the source-bound normal victory voice for tutorial battle 5000 only."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'analysis/battle-visual/elsa-audio'
OUT=ROOT/'clients/cocos-poc/assets/resources/recovered/result-audio'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    links=json.loads((ROOT/'analysis/battle-ui/result/audio-links.json').read_text('utf8'))
    routes=json.loads((SOURCE/'result-voice-routes.json').read_text('utf8'))
    decoded=json.loads((SOURCE/'result-voice-decode-report.json').read_text('utf8'))
    mix=json.loads((SOURCE/'result-voice-mix-ancestry.json').read_text('utf8'))
    if decoded['source_report_sha256']!=digest(SOURCE/'result-voice-routes.json') or mix['bank_sha256']!=routes['bank_sha256']:
        raise ValueError('Victory audio evidence changed')
    normal=next(e for e in links['voice_events'] if e['key']=='BATTLE_WIN_NORMAL')
    event=next(e for e in routes['events'] if e['id']==int(normal['event']['Id']))
    if len(event['actions'])!=1 or event['actions'][0]['node_class']!='CAkActionPlay':raise ValueError('Unexpected result audio actions')
    action=event['actions'][0]
    if action['timing_properties']:raise ValueError('Unexpected authored timing')
    sound=action['target'];media=next(m for m in decoded['media'] if m['id']==sound['media_id'])
    chain=mix['chains'][str(sound['id'])]
    db=sum(float(v['value']) for n in chain for p in n['properties'] if int(p['id']['value'])==0
           for v in p['values'] if v['name']=='pValue' and v.get('float_verified'))
    volume=10**(db/20)
    if volume*.8>1:raise ValueError('Insufficient audio headroom')
    pcm=SOURCE/'result-voice-pcm'/f"{sound['media_id']}.wav"
    if digest(pcm)!=media['pcm_sha256']:raise ValueError('PCM changed')
    OUT.mkdir(parents=True,exist_ok=True);(OUT/pcm.name).write_bytes(pcm.read_bytes())
    manifest=dict(master_volume=.8,cues=[dict(clip='result',ratio=0,event=normal['event']['Name'],
        resource='recovered/result-audio/'+pcm.stem,volume=volume,static_volume_db=db,pcm_sha256=media['pcm_sha256'])],
        inputs={name:digest(SOURCE/name) for name in ('result-voice-routes.json','result-voice-decode-report.json','result-voice-mix-ancestry.json')},
        limitations=['Only tutorial battle 5000 / Elsa / normal victory is wired.',
            'Default immediate Play inferred from absent action timing; original runtime unverified.',
            'Preview master .8 and static ancestry gain omit Wwise buses, RTPC and effects.',
            'UI_JIESUAN has no exact metadata match and is not substituted.'])
    (OUT/'cues.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(media_id=sound['media_id'],volume=volume,duration=media['duration_seconds'])))
if __name__=='__main__':main()
