"""Resolve Future's prologue 3998/1703 card clips from source tables.

card_table SKILL_ID -> skill_timeline_table DATA.ANIMATION_LIST -> the
recovered battle-actions export's ANIM_STATES_* names. Writes
analysis/prologue-boss/future-actions/report.json for the UE setup.
"""
import hashlib
import json
from pathlib import Path

from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'clients/unreal5 5.8/Source/Hczs/Private/Tests/Fixtures/prologue-boss-party-v1.json'
EXPORT = ROOT / 'analysis/characters/hero-003/battle-actions/export/export-report.json'
OUT = ROOT / 'analysis/prologue-boss/future-actions/report.json'
CARD_TABLE, TIMELINE_TABLE = 3391, 6655
GLB_SHA = '8b9316a21ee2977704d8a0ffff0b2c35c2980b77710887493c1059bcce0c79bd'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    export_raw = EXPORT.read_bytes()
    export = json.loads(export_raw)
    glb = Path(export['output'])
    selection = export['selection']
    if export['sha256'] != GLB_SHA or sha(glb.read_bytes()) != GLB_SHA:
        raise ValueError('Future battle-actions GLB changed')
    if selection['characterId'] != 3 or selection['purpose'] != 'battle-actions':
        raise ValueError('Export is not Future battle actions')
    states = selection['actionStates']
    clips = sorted(set(states.values()))
    definition = json.loads(FIXTURE.read_text('utf8'))['initial']['battle']['scenario']['definition']
    if [m['id'] for m in definition['party']] != ['1', '3']:
        raise ValueError('Boss party definition changed')
    cards = sorted({entry['cardId'] for entry in definition['deck'] if entry['ownerId'] == '3'})
    card_table = export_table(CARD_TABLE, {int(c) for c in cards})
    card_rows = {row['id']: row['fields'] for row in card_table['rows']}
    timelines = export_table(TIMELINE_TABLE)
    by_skill = {}
    for row in timelines['rows']:
        by_skill.setdefault(row['fields'].get('OwnerSkill'), []).append(row)
    card_clips, evidence = {}, []
    for card in cards:
        skill = card_rows[int(card)]['SKILL_ID']
        rows = by_skill.get(skill, [])
        if len(rows) != 1:
            raise ValueError(f'Card {card} skill {skill} has {len(rows)} timelines')
        animation = rows[0]['fields']['DATA']['ANIMATION_LIST']
        if len(animation) != 1 or 'ANIM_STATES_' + animation[0] not in states:
            raise ValueError(f'Card {card} timeline state is not a recovered single clip: {animation}')
        clip = states['ANIM_STATES_' + animation[0]]
        card_clips[card] = clip
        evidence.append(dict(cardId=card, name=definition['cards'][card]['name'], skillId=skill, timelineId=rows[0]['id'],
                             animationState=animation[0], clip=clip, timelineSource=rows[0]['source']))
    report = dict(format='hczs-prologue-ally-actions-v1', characterId=3, memberIndex=1,
                  glb=str(glb), glbSha256=GLB_SHA, exportReportSha256=sha(export_raw),
                  clips=clips, actionStates=states, cardClips=card_clips, cards=evidence,
                  sourceTables=dict(card=card_table['source'], timeline=timelines['source']),
                  reconstruction=['Damage to party member 1 plays HIT_1; defeat plays DIE; SHOW plays with the Elsa entrance.',
                                  'Card clips follow skill timelines; their VFX, SFX and timeline event offsets are not ported.'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, ensure_ascii=False, indent=2).encode('utf8')
    OUT.write_bytes(raw)
    print(json.dumps(dict(report=str(OUT), sha256=sha(raw), cardClips=card_clips), ensure_ascii=False))


if __name__ == '__main__':
    main()
