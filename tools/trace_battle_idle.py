"""Locate hash-verified animation state selection; never execute APK scripts."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/battle-idle'
TERMS = (b'stand_idle', b'stand_ready', b'IDLE_1', b'fight_idle_show')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    matches = []
    for row in rows:
        if not row.get('decoded_sha256'):
            continue
        raw = (ROOT/row['output']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['decoded_sha256']:
            raise ValueError('Script hash changed')
        if not any(term in raw for term in TERMS):
            continue
        module = static.read_module(row)
        names = []
        for _, code in static.walk_codes(module):
            values = code['consts'] + code['names']
            if any(isinstance(value, bytes) and any(term in value for term in TERMS) for value in values):
                names.append(code['name'].decode('utf8'))
        if names:
            report = static.export(row, selected_names=names)
            target = OUT/f"{row['index']}.json"
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
            matches.append(dict(index=row['index'], filename=row['filename'], functions=names,
                                report=str(target.relative_to(ROOT)), sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (OUT/'index.json').write_text(json.dumps(dict(evidence='Hash-verified local static scripts; not native runtime or REA Evidence',
        terms=[t.decode() for t in TERMS], matches=matches), ensure_ascii=False, indent=2), 'utf8')
    from inspect_neox_animation import parse_library, parse_clip, clip_path, extract_with_provenance, map_bones
    from inspect_neox_model import parse_model
    from neox_resource_paths import read_catalogue
    from extract_texture_samples import APK_SHA256
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    library = parse_library((ROOT/'analysis/animation/recovered/ailisha.gisacl').read_bytes())
    mesh = (ROOT/'analysis/battle-visual/scene-export/source/File_26.mesh').read_bytes()
    if library['sha256'] != '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41' or hashlib.sha256(mesh).hexdigest() != '37475c3438660c0cff65febfdf908a8aaec918344db1a6a547ef893b59e6b3f5':
        raise ValueError('Actor source changed')
    catalogue = read_catalogue(apk)
    path = OUT/'idle_1.gisacl'
    provenance = extract_with_provenance(apk, catalogue, clip_path('character/player/ailisha/ailisha.gisacl', 'idle_1'), path, APK_SHA256)
    parsed = parse_clip(path.read_bytes())
    parsed['source'] = provenance
    parsed['library_record'] = next(r for r in library['clips'] if r['name'] == 'idle_1')
    parsed['bone_mapping'] = map_bones(library, parsed, [b['name'] for b in parse_model(mesh)['bones']])
    (OUT/'idle_1.json').write_text(json.dumps(parsed, indent=2), 'utf8')
    print(json.dumps(matches, ensure_ascii=False))

if __name__ == '__main__':
    main()
