"""Trace shipped result-table audio names to exact Wwise metadata, without guessing aliases."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from extract_game_data import export_table
from trace_elsa_voice import main as voice_routes
from trace_first_encounter import literal_table
import inspect_battle_rules as static

ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'analysis/battle-ui/result';out.mkdir(parents=True,exist_ok=True)
    voices=export_table(441)
    voices['rows']=[r for r in voices['rows'] if r['id'] in ('BATTLE_WIN_NORMAL','BATTLE_WIN_BOSS')]
    ui=export_table(3873)
    ui['rows']=[r for r in ui['rows'] if r['id']=='UI_JIESUAN']
    if len(voices['rows'])!=2 or len(ui['rows'])!=1:raise ValueError('Missing result audio rows')
    metadata=ROOT/'analysis/battle-visual/enemy-audio/SoundbanksInfo.xml'
    tree=ET.parse(metadata)
    rows=[];ids=[]
    for row in voices['rows']:
        path=row['fields']['1'];name=path.split('|')[1]
        matches=[(b,e) for b in tree.findall('.//SoundBank') for e in b.findall('IncludedEvents/Event') if e.get('Name')==name]
        if len(matches)!=1:raise ValueError('Victory voice event not unique')
        bank,event=matches[0]
        if bank.findtext('ShortName')!='ailisha_voice':raise ValueError('Unexpected victory voice bank')
        ids.append(int(event.get('Id')))
        rows.append(dict(key=row['id'],character_id=1,path=path,bank=bank.findtext('Path'),event=dict(event.attrib)))
    voice_routes(tuple(ids),'result-voice-routes.json')
    battle=literal_table(4664,{5000})
    if battle['rows'][0]['fields']['SceneType']!=0:raise ValueError('Tutorial scene type changed')
    script_rows={r['index']:r for r in json.loads((static.SCRIPT/'index.json').read_text('utf8'))}
    for index,names in ((8434,('getBattleIsBoss','getDungeonBattleType')),(6048,('getDungeonBattleType',)),(9613,('getMazeTable','isBattle')),(6221,('SceneType',))):
        (out/f'audio-branch-{index}.json').write_text(json.dumps(static.export(script_rows[index],selected_names=names),ensure_ascii=False,indent=2),'utf8')
    ui_path=ui['rows'][0]['fields']['ClipPath'];ui_name=ui_path.split('|')[1]
    ui_matches=[dict(bank=b.findtext('ShortName'),event=dict(e.attrib)) for b in tree.findall('.//SoundBank')
                for e in b.findall('IncludedEvents/Event') if e.get('Name')==ui_name]
    report=dict(evidence_kind='Local static extraction; not original runtime or REA Evidence',
        voice_table=voices,ui_table=ui,voice_events=rows,ui_exact_matches=ui_matches,
        tutorial_battle=battle,
        metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
        route_report='analysis/battle-visual/elsa-audio/result-voice-routes.json',
        limitations=['UI_JIESUAN aliases are not guessed when exact event metadata is absent.',
            'Result playback timing, bus/RTPC mixing and original runtime remain unverified.'])
    (out/'audio-links.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(voice_events=rows,ui_exact_match_count=len(ui_matches))))

if __name__=='__main__':main()
