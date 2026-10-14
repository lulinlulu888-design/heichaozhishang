"""Resolve source MusicTriggers without normalizing significant separators."""
import json
import math
import xml.etree.ElementTree as ET

from extract_npk import ROOT, APK
from inspect_enemy_audio import sha
from inspect_neox_model import extract_npk_entry
from neox_resource_paths import string_id_legacy


def trace(path, expected_hash):
    data = path.read_bytes()
    if sha(data) != expected_hash:
        raise ValueError('MusicTriggers identity mismatch')
    root = ET.fromstring(data)
    names = {}
    for obj in root.findall('.//BoundObject/Object'):
        name = obj.get('Name')
        ident = string_id_legacy(name.encode('utf8'))
        if ident in names and names[ident] != name:
            raise ValueError('ambiguous sound hash')
        names[ident] = name
    rows = []
    for clip in root.find('Triggers'):
        for cue in clip:
            ratio = float(cue.get('TimeRatio'))
            if not math.isfinite(ratio) or not 0 <= ratio <= 1:
                raise ValueError('unsupported trigger ratio')
            for trigger in cue:
                ident = int(trigger.get('ObjectFileID')) & 0xffffffff
                name = names[ident]
                if trigger.get('ObjectFileName') not in (None, name):
                    raise ValueError('explicit file name disagrees with hashed binding')
                bank, event = name.split('/Event|')
                rows.append(dict(clip=clip.tag, cue=cue.tag, time_ratio=ratio,
                                 object_id=ident, object_name=name, bank_reference=bank,
                                 event=event, source_attributes=trigger.attrib))
    return dict(source=str(path.relative_to(ROOT)), sha256=sha(data),
                unique_trigger_ids=len({r['object_id'] for r in rows}), cues=rows)


def main():
    out = ROOT/'analysis/battle-visual/elsa-audio'
    extract_npk_entry(APK, 'assets/res/character.npk', 6122, out/'ailisha_music.ags')
    elsa = trace(out/'ailisha_music.ags',
                 '90287a47b0b2cfa55e866d539fa8016e9953e6c1119b84e5cb5f9a513984ec8a')
    enemy = trace(ROOT/'analysis/battle-visual/enemy-skills/enemy-music.ags',
                  'a1b79f1bfdf3c631231bdb410606ce1cda4ab7d3ebc0ed4ab8085ad9159acb26')
    routes = json.loads((out/'event-routes.json').read_text('utf8'))
    by_name = {r['event']['Name']:r for r in routes['routes']}
    for cue in elsa['cues']:
        if cue['bank_reference'] == 'wwise/ailisha_skill.bnk:ailisha_skill':
            route = by_name.get(cue['event'])
            cue['verified_bank_route'] = route
            cue['route_status'] = 'resolved' if route and all('media' in a for a in route['actions']) else 'incomplete'
        else:
            cue['route_status'] = 'other bank; not resolved by ailisha_skill evidence'
    report = dict(elsa=elsa, enemy=enemy, algorithm='StringIDLegacy over exact UTF-8 Object.Name bytes',
                  limitations=['Do not apply resource_hash separator normalization to sound object identifiers.',
                               'TimeRatio is source data, not original-client wall-clock measurement.',
                               'Bank references are preserved exactly, including legacy aliases.',
                               'No Wwise mixing properties, playback or client integration implemented.'])
    (out/'animation-cues.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(elsa_unique_ids=elsa['unique_trigger_ids'],elsa_cues=len(elsa['cues']),
                          enemy_unique_ids=enemy['unique_trigger_ids'],enemy_cues=len(enemy['cues']))))


if __name__ == '__main__':
    main()
