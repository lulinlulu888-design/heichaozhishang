"""Extract original entity-0 HIT_1/DIE clips; static evidence, not runtime selection."""
import hashlib
import json
from pathlib import Path
from inspect_neox_animation import parse_library, parse_clip, clip_path, extract_with_provenance, map_bones
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/player-reactions'


def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    entity = json.loads((ROOT/'analysis/resource-mapping/entity-table-selected.json').read_text('utf8'))
    fields = next(r['fields'] for r in entity['rows'] if r['id'] == 0)
    mapping = {k: fields[k] for k in ('ANIM_STATES_DIE', 'ANIM_STATES_HIT_1', 'ANIM_STATES_HIT_2')}
    if mapping != dict(ANIM_STATES_DIE='death', ANIM_STATES_HIT_1='hit_2', ANIM_STATES_HIT_2='hit_1'):
        raise ValueError('Entity mapping changed')
    library = parse_library((ROOT/'analysis/animation/recovered/ailisha.gisacl').read_bytes())
    mesh = (ROOT/'analysis/battle-visual/scene-export/source/File_26.mesh').read_bytes()
    if library['sha256'] != '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41' or hashlib.sha256(mesh).hexdigest() != '37475c3438660c0cff65febfdf908a8aaec918344db1a6a547ef893b59e6b3f5':
        raise ValueError('Actor source changed')
    model = parse_model(mesh)
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('hit_2', 'death'):
        path = OUT/(name+'.gisacl')
        source = extract_with_provenance(apk, catalogue,
            clip_path('character/player/ailisha/ailisha.gisacl', name), path, APK_SHA256)
        parsed = parse_clip(path.read_bytes())
        parsed['source'] = source
        parsed['library_record'] = next(r for r in library['clips'] if r['name'] == name)
        parsed['bone_mapping'] = map_bones(library, parsed, [b['name'] for b in model['bones']])
        (OUT/(name+'.json')).write_text(json.dumps(parsed, indent=2), encoding='utf8')
    (OUT/'mapping.json').write_text(json.dumps(dict(entity_id=0, entity_source=entity['source'],
        mapping=mapping, selected=['hit_2', 'death'],
        scope='HIT_1 selected for reconstructed reaction; original HIT_1/HIT_2 selection not established'), indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
