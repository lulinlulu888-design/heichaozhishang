"""Link original first-battle timeline animation names to Elsa clip payloads.

Static data evidence only: no claim that a timeline list is a fixed runtime
sequence, and no execution of APK code or unvalidated native ACL sampling.
"""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from export_elsa_model import write_json
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_library, parse_clip, clip_path, extract_with_provenance, map_bones
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/skill-animation'


def checked_json(relative):
    path = ROOT/relative
    return json.loads(path.read_text('utf8')), hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    timelines, timeline_sha = checked_json('analysis/first-encounter/skill-timelines.json')
    entities, entity_sha = checked_json('analysis/resource-mapping/entity-table-selected.json')
    entity = next(r for r in entities['rows'] if r['id'] == 0)
    library_path = 'character/player/ailisha/ailisha.gisacl'
    library = parse_library((ROOT/'analysis/animation/recovered/ailisha.gisacl').read_bytes())
    if library['sha256'] != '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41':
        raise ValueError('Animation library changed')
    mesh = (ROOT/'analysis/battle-visual/scene-export/source/File_26.mesh').read_bytes()
    if hashlib.sha256(mesh).hexdigest() != '37475c3438660c0cff65febfdf908a8aaec918344db1a6a547ef893b59e6b3f5':
        raise ValueError('Scene actor mesh changed')
    model = parse_model(mesh)
    catalogue = read_catalogue(apk)
    wanted = {110001, 110009, 210003, 410101, 410102}
    links, clips = [], {}
    for row in timelines['rows']:
        fields = row['fields']
        if fields.get('OwnerSkill') not in wanted or fields.get('TYPE') != 0:
            continue
        types = fields['DATA']['ANIMATION_LIST']
        names = [entity['fields']['ANIM_STATES_'+t] for t in types]
        links.append(dict(timeline=row, animation_types=types, clip_names=names))
        for name in names:
            if name in clips:
                continue
            record = next(r for r in library['clips'] if r['name'] == name)
            out = OUT/(name+'.gisacl')
            source = extract_with_provenance(apk, catalogue, clip_path(library_path, name), out, APK_SHA256)
            data = out.read_bytes()
            parsed = parse_clip(data)
            parsed['bone_mapping'] = map_bones(library, parsed, [b['name'] for b in model['bones']])
            parsed['source'] = source
            parsed['library_record'] = record
            write_json(OUT/(name+'.json'), parsed)
            clips[name] = parsed
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    for module_id, functions in [(7810, ('SkillPlayAnimationAction','doInit','play')),
                                  (2072, ('getSkillDurationAndReactTimeList',))]:
        row = next(r for r in index if r['index'] == module_id)
        write_json(OUT/f'{module_id}-actions.json', static.export(row, functions))
    result = dict(evidence_kind='Hash-checked local static data and partial bytecode; not REA runtime Evidence',
        apk_sha256=APK_SHA256, timeline_source=timelines['source'], timeline_json_sha256=timeline_sha,
        entity_source=entities['source'], entity_json_sha256=entity_sha,
        entity_id=0, library_sha256=library['sha256'], links=links, clips=clips,
        unresolved=['Animation randomisation and actual state-machine sequence',
                    'Attack-event timestamps and root-motion application',
                    'Full ACL layout validation and native sampling of these new clips',
                    'Rendered attack/hit effects and timing'])
    write_json(OUT/'mapping.json', result)
    print(json.dumps(dict(links=[dict(skill=r['timeline']['fields']['OwnerSkill'], clips=r['clip_names']) for r in links],
        clips={k:dict(samples=v['samples'], duration=v['duration_seconds'], bones=v['bone_count']) for k,v in clips.items()}), ensure_ascii=False))


if __name__ == '__main__':
    main()
