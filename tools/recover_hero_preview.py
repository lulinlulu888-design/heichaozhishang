"""Recover a configured hero LOD0 and exact hall/battle idle via shared tools.

Only APK bytes are input. Output is a skinned color-reference animation GLB,
not original NeoX shading, physics or a complete playable character.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from decode_ktx import parse_ktx
from export_elsa_model import extract, parse_materials, bind_materials, write_json
from export_lynn_model import export_character, drop_unanimated_leaf_bones
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_library, parse_clip, clip_path, map_bones
from inspect_neox_model import parse_model, summary
from neox_resource_paths import read_catalogue
from sample_lynn_idle import sample_pinned
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
# Battle entity animation states sampled for --purpose battle-actions (idle first).
BATTLE_ACTION_STATES = ('ANIM_STATES_IDLE_1', 'ANIM_STATES_SHOW', 'ANIM_STATES_ATK_1', 'ANIM_STATES_HIT_1',
                        'ANIM_STATES_HIT_2', 'ANIM_STATES_DIE', 'ANIM_STATES_SHD_UP_1', 'ANIM_STATES_SPL_1')


def select_character(character_id, purpose):
    character = literal_table(8995, {character_id})
    if len(character['rows']) != 1 or character['rows'][0]['fields'].get('UseRole') != 1:
        raise ValueError('Expected one configured UseRole=1 hero')
    fields = character['rows'][0]['fields']
    entity = literal_table(1955, {fields['CULTIVATE_ENTITY_ID' if purpose == 'hall' else 'ENTITY_ID']})
    if len(entity['rows']) != 1:
        raise ValueError('Missing source entity')
    ef = entity['rows'][0]['fields']
    lod = literal_table(1268, {ef['LOD_ID']})
    levels = literal_table(6328, set(lod['rows'][0]['fields']['LOD_MODEL_LIST']))
    lod0 = [row for row in levels['rows'] if row['fields']['LEVEL'] == 0]
    state = 'ANIM_STATES_HOME_STAND_IDLE' if purpose == 'hall' else 'ANIM_STATES_IDLE_1'
    if len(lod0) != 1 or not ef.get(state):
        raise ValueError('Unique LOD0 or explicit idle state unavailable; no fallback chosen')
    states = {}
    if purpose == 'battle-actions':
        states = {name: ef[name] for name in BATTLE_ACTION_STATES if ef.get(name)}
    return dict(characterId=character_id, name=fields['NAME'], initial=fields['InitChar'],
        purpose=purpose, entityId=entity['rows'][0]['id'], model=lod0[0]['fields']['MODEL_PATH'],
        clip=ef[state], state=state, actionStates=states,
        modelSelection='Source LEVEL=0 for inspection; runtime LOD selection unobserved',
        sourceTables=dict(character=character, entity=entity, lod=lod, levels=levels))


def recover(character_id, purpose, apk, catalogue):
    selected = select_character(character_id, purpose)
    out = ROOT / 'analysis/characters' / ('hero-' + str(character_id).zfill(3))
    out.mkdir(parents=True, exist_ok=True)
    sources = {}

    def get(logical):
        if logical not in sources:
            target = out / 'source' / (hashlib.sha256(logical.encode()).hexdigest()[:20] + Path(logical).suffix)
            sources[logical] = extract(apk, catalogue, logical, target, APK_SHA256)
        path = Path(sources[logical]['sample_path'])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sources[logical]['sha256']:
            raise ValueError('Extracted source changed')
        return raw

    model_path = selected['model']
    gim = get(model_path)
    xml = ET.fromstring(gim)
    mesh_path = model_path[:-4] + '.mesh'
    if xml.get('Mesh', mesh_path).replace('\\','/') != mesh_path.replace('\\','/'):
        raise ValueError('This exporter needs an explicit adapter for a non-sibling mesh')
    model = parse_model(get(mesh_path), repair_normals=True)
    materials = parse_materials(get(model_path[:-4]+'.mtg'), expected_slots=None)
    bindings = bind_materials(model, gim, materials, allow_bounds_mismatch=True)
    selected['boundsMismatchedSubmeshes'] = [row['submesh_index'] for row in bindings if row['bounds_max_error'] > 1e-4]
    selected['normalRepairs'] = model.get('normal_repairs')
    texture_sources = {}
    for material in materials:
        for key, path in material['params'].items():
            if key.startswith('Tex') and '/' in path.replace('\\','/'):
                candidate = path.rsplit('.',1)[0].replace('\\','/') + '.ktx'
                texture_sources[candidate] = parse_ktx(get(candidate))
    libraries = [e.attrib['value'] for e in xml.findall('GisFiles/*')]
    if len(libraries) != 1:
        raise ValueError('Animation library is missing or ambiguous')
    library_path = libraries[0]
    library = parse_library(get(library_path), allow_empty_roots=True)
    model = drop_unanimated_leaf_bones(model, library['bone_names'])
    selected['droppedUnanimatedLeafBones'] = model.get('dropped_unanimated_leaf_bones', [])
    clip_name = selected['clip']
    clip_names = list(dict.fromkeys([clip_name, *selected['actionStates'].values()]))
    mesh_bones = [b['name'] for b in model['bones']]
    selected['libraryOnlyBones'] = sorted(set(library['bone_names']) - set(mesh_bones))
    clip_directory = out / purpose / 'poses'
    clip_directory.mkdir(parents=True, exist_ok=True)
    pins, scale_formats = {}, set()
    for name in clip_names:
        records = [row for row in library['clips'] if row['name'] == name]
        if len(records) != 1:
            raise ValueError('Configured clip is not unique in this model library: ' + name)
        clip_raw = get(clip_path(library_path, name))
        parsed = parse_clip(clip_raw)
        mapping = map_bones(library, parsed, mesh_bones, allow_library_extras=True)
        scale_formats.add(clip_raw[parsed['acl_offset'] + 25])
        (clip_directory / (name+'.gisacl')).write_bytes(clip_raw)
        parsed.update(source=sources[clip_path(library_path, name)], library_sha256=library['sha256'],
            library_record=records[0], bone_mappings={mesh_path:mapping})
        write_json(clip_directory / (name+'.json'), parsed)
        pins[name] = parsed['acl_sha256']
    if len(scale_formats) != 1 or not scale_formats <= {0, 1}:
        raise ValueError('Unsupported or mixed source ACL scale formats')
    scale_format = scale_formats.pop()
    audit = dict(apk_sha256=APK_SHA256, selection=selected, models=[dict(path=model_path,
        mesh=summary(model), materials=materials, bindings=bindings, libraries=libraries)],
        sources=sources, textures=texture_sources)
    # export_character reads a model audit next to its output folder. Keep each
    # purpose self-contained so another export cannot replace its evidence.
    audit_directory = out / purpose
    write_json(audit_directory / 'asset-audit.json', audit)
    sample_pinned(clip_directory, pins, 'hero-' + str(character_id) + '-' + purpose, scale_format,
                  allow_single_segment_no_range=purpose == 'battle-actions')
    export_character(audit_directory / 'export', model_path, library_path, clip_name,
        'Hero' + str(character_id).zfill(3), clip_directory, extra_clips=clip_names[1:],
        output_suffix='battle-actions' if purpose == 'battle-actions' else 'idle')
    report_path = audit_directory / 'export/export-report.json'
    result = json.loads(report_path.read_text('utf8'))
    result.update(sourceApkSha256=APK_SHA256, selection=selected,
        auditSha256=hashlib.sha256((audit_directory/'asset-audit.json').read_bytes()).hexdigest(),
        recoveryScope='Exact configured idle sampled on LOD0; source geometry/skin/color preserved. UE playback, NeoX materials, physics and gameplay integration unverified.')
    write_json(report_path, result)
    return dict(characterId=character_id, name=selected['name'], purpose=purpose,
        output=result['output'], sha256=result['sha256'], animation=clip_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('character_ids', type=int, nargs='+')
    parser.add_argument('--purpose', choices=('hall','battle','battle-actions'), default='hall')
    args = parser.parse_args()
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Original APK changed')
    catalogue = read_catalogue(apk)
    results = []
    for hid in dict.fromkeys(args.character_ids):
        try:
            results.append(dict(passed=True, **recover(hid, args.purpose, apk, catalogue)))
        except Exception as error:
            results.append(dict(characterId=hid, purpose=args.purpose, passed=False,
                errorType=type(error).__name__, error=str(error)))
    write_json(ROOT / 'analysis/characters' / ('batch-'+args.purpose+'.json'),
        dict(apkSha256=APK_SHA256, results=results, scope='Source color/idle conversion only; per-character failures do not abort the remaining batch.'))
    print(json.dumps(results, ensure_ascii=False))
    if any(not row['passed'] for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
