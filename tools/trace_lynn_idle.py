"""Extract Lynn's source idle clip and verify all four mesh skeleton mappings."""
import json
from pathlib import Path
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import (file_sha256, parse_library, parse_clip,
    clip_path, extract_with_provenance, map_bones, save_json)
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/characters/lynn/idle'

def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if file_sha256(apk) != APK_SHA256:
        raise ValueError('APK changed')
    audit = json.loads((OUT.parent/'asset-audit.json').read_text('utf8'))
    def source(logical):
        record = audit['sources'][logical]
        path = Path(record['sample_path'])
        if file_sha256(path) != record['sha256']:
            raise ValueError('Audited source changed: '+logical)
        return path.read_bytes()
    library_path = 'character\\player\\lin\\lin.gisacl'
    library = parse_library(source(library_path), allow_empty_roots=True)
    entity = export_table(1955, {11})
    if entity['rows'][0]['fields']['ANIM_STATES_IDLE_1'] != 'idle_1':
        raise ValueError('Source battle idle selection changed')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/'idle_1.gisacl'
    provenance = extract_with_provenance(apk, read_catalogue(apk),
        clip_path(library_path, 'idle_1'), path, APK_SHA256)
    raw = path.read_bytes()
    parsed = parse_clip(raw)
    mappings = {}
    for logical in audit['sources']:
        if logical.endswith('.mesh'):
            model = parse_model(source(logical))
            mappings[logical] = map_bones(library, parsed, [b['name'] for b in model['bones']])
    if len(mappings) != 4:
        raise ValueError('Expected all four audited mesh skeletons')
    parsed.update(source=provenance, entity=entity,
        library_sha256=library['sha256'],
        library_record=next(c for c in library['clips'] if c['name']=='idle_1'),
        bone_mappings=mappings,
        acl_format_bytes=list(raw[parsed['acl_offset']+20:parsed['acl_offset']+27]),
        evidence='Hash-verified local static parsing; not original runtime evidence')
    save_json(OUT/'idle_1.json', parsed)
    print(json.dumps({k:parsed[k] for k in ['acl_sha256','bone_count','samples','sample_rate','acl_format_bytes','library_record']}))

if __name__ == '__main__':
    main()
