"""Shared native audio packaging checks; no playback claims."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_audio(check, bundle, paths, packaged_hashes):
    assets = ROOT/'legacy/cocos-poc/assets'
    check('BattleAudio template matches client', (assets/'BattleAudio.ts').read_bytes()==
          (ROOT/'tools/templates/cocos-battle-audio.ts').read_bytes())
    check('Audio playback and cancellation compiled', all(s in bundle for s in
          ('recovered/audio/cues','HCZS_AUDIO','cancelled','OriginalBattleSound')))
    manifest = json.loads((assets/'resources/recovered/audio/cues.json').read_text('utf8'))
    cues = manifest['cues']
    effects = [c for c in cues if 'variants' not in c]
    voice = [c for c in cues if 'variants' in c]
    streams = [v for c in cues for v in c.get('variants',[c])]
    source = ROOT/'analysis/battle-visual/elsa-audio'
    voice_evidence = json.loads((source/'battle-voice-cues.json').read_text('utf8'))
    check('Voice evidence inputs remain unchanged',all(
          hashlib.sha256((source/name).read_bytes()).hexdigest()==digest
          for name,digest in voice_evidence['inputs'].items()))
    expected = {r['cue']['clip']:r for r in voice_evidence['cues']}
    check('Voice timing, sequence order and gains match recovered evidence',len(voice)==len(expected) and all(
          c['event']==expected[c['clip']]['cue']['event'] and
          c['ratio']==expected[c['clip']]['cue']['time_ratio'] and
          c['delay']==expected[c['clip']]['play_delay_ms']/1000 and
          c['fade']==expected[c['clip']]['stop_transition_ms']/1000 and
          c['group']==str(expected[c['clip']]['stop_group']) and
          c['sequence']==str(expected[c['clip']]['container_id']) and
          [(v['sound_id'],v['volume'],v['pcm_sha256']) for v in c['variants']]==
          [(v['sound_id'],v['static_linear_gain'],v['media']['pcm_sha256']) for v in expected[c['clip']]['variants']]
          for c in voice))
    check('Preview master preserves gain without clipping',manifest['master_volume']==0.8 and
          all(0<=v['volume']*manifest['master_volume']<=1 for v in streams))
    check('Set cleanup avoids Creator loose spread regression',
          all('[].concat(this.'+name+')' not in bundle for name in ('pending','voices','delayed')) and
          'Array.from(this.pending)' in bundle)
    check('Four source audio cue resources exported',len(effects)==4 and
          {c['clip'] for c in effects}=={'crit_1','death','fire_1_1','fire_1_3'} and
          'recovered/audio/cues' in paths and all(c['resource'] in paths for c in effects))
    check('Three voice cues and source streams exported',len(voice)==3 and
          {c['clip'] for c in voice}=={'crit_1','fire_1','fire_1_3'} and
          all(v['resource'] in paths for c in voice for v in c['variants']))
    check('PCM sources match cue provenance',all(
          hashlib.sha256((assets/'resources'/(c['resource']+'.wav')).read_bytes()).hexdigest()==c['pcm_sha256']
          for c in streams))
    check('All exact PCM streams packaged',all(c['pcm_sha256'] in packaged_hashes for c in streams))
