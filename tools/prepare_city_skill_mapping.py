"""Build city skill -> original entity animation mapping from verified literals."""
import hashlib
import json
from pathlib import Path
from trace_first_encounter import literal_table, extra_index

ROOT = Path(__file__).resolve().parents[1]


def main():
    ids = {66051, 66052, 66053, 66054}
    skills = literal_table(9333, ids)
    index = extra_index(6655, ids)
    timeline_ids = {entry for value in index['requested'].values() for entry in value['value']}
    timelines = literal_table(6655, timeline_ids)
    entity = literal_table(1955, {6605})
    fields = entity['rows'][0]['fields']
    if any(row['fields']['CLIENT_SKILL_REPLACE'] != 0 for row in skills['rows']):
        raise ValueError('Skill replacement must be resolved before binding')
    mapping = {}
    for row in timelines['rows']:
        timeline = row['fields']
        skill = str(timeline['OwnerSkill'])
        states = timeline['DATA']['ANIMATION_LIST']
        if skill in mapping or timeline['TIME'] != 0 or timeline['TYPE'] != 0 or len(states) != 1:
            raise ValueError('Unsupported city animation timeline')
        mapping[skill] = fields['ANIM_STATES_' + states[0]]
    if mapping != {'66051': 'fire', '66052': 'fire', '66053': 'skill_3', '66054': 'skill_2'}:
        raise ValueError('Reviewed city animation mapping changed')
    payload = dict(schema='hczs-city-skill-animation-v1', encounter='city-preview-10405', enemyId='6605',
        clips=mapping, tables=dict(skills=skills, timelines=timelines, entity=entity), reverseIndex=index,
        originalRuntimeVerified=False, effectsAndHitSchedulingVerified=False)
    out = ROOT / 'analysis/unreal/city-preview/skill-mapping.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(clips=mapping, sha256=hashlib.sha256(out.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
