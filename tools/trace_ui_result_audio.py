"""Bound UI_JIESUAN through Python call sites and scan exact candidate event IDs."""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
import inspect_battle_rules as static
from extract_game_data import export_table
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import chunks
from scan_enemy_audio_banks import objects

ROOT=Path(__file__).resolve().parents[1]

def event_hash(name):
    # Candidate Wwise name-ID mapping; corroborated against every metadata event below.
    value=2166136261
    for byte in name.lower().encode('utf8'):value=((value*16777619)&0xffffffff)^byte
    return value

def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    out=ROOT/'analysis/battle-ui/result';out.mkdir(parents=True,exist_ok=True)
    rows={r['index']:r for r in json.loads((static.SCRIPT/'index.json').read_text('utf8'))}
    sources=[]
    for number,names in ((999,('onFirstUpdate',)),(8308,('__init__','<dictcomp>','playUIEvent')),
                          (8452,('ui_sound_channel_noncover','play'))):
        report=static.export(rows[number],selected_names=names)
        path=out/f'ui-audio-{number}.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    table=export_table(3873);entry=next(r for r in table['rows'] if r['id']=='UI_JIESUAN')
    path=entry['fields']['ClipPath'];name=path.split('|')[1]
    metadata=ROOT/'analysis/battle-visual/enemy-audio/SoundbanksInfo.xml'
    events=ET.parse(metadata).findall('.//IncludedEvents/Event')
    distinct={(e.get('Name'),int(e.get('Id'))) for e in events}
    mismatches=[dict(name=n,id=i,computed=event_hash(n)) for n,i in sorted(distinct) if event_hash(n)!=i]
    if mismatches:raise ValueError('Name-ID mapping does not match metadata: '+str(mismatches[:3]))
    # Both are hypotheses at the native audio.event boundary; neither is asserted
    # to be the actual input to GetIDFromString in this game build.
    candidates={name:event_hash(name),path:event_hash(path)}
    banks=[]
    with zipfile.ZipFile(apk) as archive:
        for member in sorted(n for n in archive.namelist() if n.endswith('.bnk')):
            raw=archive.read(member);parts=chunks(raw)
            records=objects(parts[b'HIRC'][1]) if b'HIRC' in parts else []
            banks.append(dict(member=member,sha256=hashlib.sha256(raw).hexdigest(),
                object_count=len(records),matches=[r for r in records if r['id'] in candidates.values()]))
    report=dict(evidence_kind='Ordinary local static tools; not original runtime or REA Evidence',
        apk_sha256=APK_SHA256,script_evidence=sources,table_source=table['source'],entry=entry,
        python_path=['ResultDialog.onFirstUpdate: playUIEvent(UI_JIESUAN, False)',
            'AudioManager: _event_music_map lookup -> _ui_event_channel_noncover.play(event_path)',
            'AudioDevice.ui_sound_channel_noncover -> DecorationChannel',
            'DecorationChannel.play -> audio.event(clip_path) -> clip.start()'],
        metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
        verified_distinct_event_pairs=len(distinct),hash_candidates=candidates,banks=banks,
        limitations=['Python passes the full table path to native audio.event without a visible alias substitution.',
            'Native audio.event parsing/alias lookup remains unresolved.',
            'Scan covers all loose BNK members only, not opaque NPK entries or downloaded banks.',
            'Candidate ID absence does not prove no semantically equivalent sound or original runtime silence.'])
    (out/'ui-audio-boundary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(metadata_pairs=len(distinct),banks=len(banks),candidates=candidates,
        matching_banks=[b['member'] for b in banks if b['matches']])))

if __name__=='__main__':main()
