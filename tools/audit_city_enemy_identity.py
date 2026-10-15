"""Resolve city enemy visual reuse from fresh literal tables and original APK bytes.

Does not alias combat IDs, enable an encounter, or assume elite placement/scale.
"""
import hashlib
import json
from pathlib import Path

from trace_first_encounter import literal_table
from inspect_neox_model import extract_npk_entry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/city-enemy'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    recovered = json.loads((ROOT / 'analysis/tutorial-enemy/export-report.json').read_text('utf8'))
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != recovered['apk_sha256']:
        raise ValueError('Original APK identity changed')
    monsters = literal_table(2363, {991, 6605})
    by_id = {row['id']: row['fields'] for row in monsters['rows']}
    if set(by_id) != {991, 6605} or any(row['ENTITY_ID'] != 6605 for row in by_id.values()):
        raise ValueError('Shared entity is not proven')
    entity = literal_table(1955, {6605})
    entity_fields = entity['rows'][0]['fields']
    lod = literal_table(1268, {entity_fields['LOD_ID']})
    lod_ids = lod['rows'][0]['fields']['LOD_MODEL_LIST']
    levels = literal_table(6328, set(lod_ids))
    primary = [row for row in levels['rows'] if row['fields']['LEVEL'] == 0]
    if len(primary) != 1 or primary[0]['fields']['MODEL_PATH'] != recovered['identity']['logical_gim']:
        raise ValueError('Recovered model differs from city LOD0')
    OUT.mkdir(parents=True, exist_ok=True)
    verified = []
    # Re-extract to a separate work directory, never overwrite the original APK.
    sources = list(recovered['sources'].values())
    sources += [item['source'] for item in recovered['texture_inventory']]
    for source in sources:
        destination = OUT / 'source' / Path(source['sample_path']).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        item = extract_npk_entry(apk, source['member'], source['index'], destination)
        if item['sha256'] != source['sha256']:
            raise ValueError(f"Recovered resource no longer matches APK: {source['logical_path']}")
        verified.append(dict(logicalPath=source['logical_path'], sha256=item['sha256'],
                             member=source['member'], index=source['index']))
    visual_keys = ('DUNGEON_ROTATION', 'DUNGEON_SCALE', 'FINAL_ROTATION', 'MIRROR_MODEL', 'OUTLINE_MODEL', 'MonsterHead')
    comparison = {key: {str(id): by_id[id].get(key) for id in by_id} for key in visual_keys}
    differences = {key: {str(id): by_id[id].get(key) for id in by_id}
                   for key in sorted(set(by_id[991]) | set(by_id[6605]))
                   if by_id[991].get(key) != by_id[6605].get(key)}
    result = dict(schema='hczs-city-enemy-visual-identity-v1', apkSha256=recovered['apk_sha256'],
                  originalApkExecuted=False, sharedEntityId=6605, sharedLod0=primary[0]['fields']['MODEL_PATH'],
                  verifiedResources=verified, tables=dict(monsters=monsters, entity=entity, lod=lod, levels=levels),
                  visualFieldComparison=comparison, monsterDifferences=differences,
                  reusableGeometryMaterialAndAnimationLibrary=True, runtimeEncounterReady=False,
                  limitations=['Shared visuals do not imply identical skill, AI, stats or battle ID.',
                               'Elite/boss scale selection and city scene placement require separate source checks.',
                               'Animation library identity does not validate each city skill timeline or VFX.'])
    (OUT / 'identity.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({k: result[k] for k in ('sharedEntityId', 'sharedLod0', 'reusableGeometryMaterialAndAnimationLibrary', 'runtimeEncounterReady')}, ensure_ascii=False))
    print(f'Verified {len(verified)} original resources; {len(differences)} monster field differences')


if __name__ == '__main__':
    main()
