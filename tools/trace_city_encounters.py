"""Join literal city scene, encounter, monster and entity data; execute no APK code."""
import json
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from trace_first_encounter import inventory, literal_table
from extract_game_data import export_table
from neox_resource_paths import lookup_logical, read_catalogue
from extract_texture_samples import APK_SHA256
from export_elsa_model import extract

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/city-scenes/encounters.json'

def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != APK_SHA256: raise ValueError('APK changed')
    catalogue = read_catalogue(apk)
    scene_table = export_table(9650)
    scenes = [r for r in scene_table['rows'] if r['fields'].get('ScenePath') in
        ('scene/city_battle_1/city_battle_1.scn','scene/city_battle_2/city_battle_2.scn')]
    ids = {r['id'] for r in scenes}
    records, errors, coverage, sources = [], [], [], []
    modules = sorted((r for r in inventory().values() if re.fullmatch(r'maze_battle_table(?:_\d+)?\.py',r['filename'].split('\\')[-1])), key=lambda r:r['index'])
    for module in modules:
        try:
            table = literal_table(module['index'])
            matches = [r for r in table['rows'] if r['fields'].get('BattleScene') in ids]
            coverage.append(dict(index=module['index'],filename=module['filename'],rows=table['total_source_rows'],matches=len(matches),sha256=module['decoded_sha256']))
            if matches:
                sources.append({k:v for k,v in table.items() if k!='rows'})
                records.extend(dict(module=module['index'],**r) for r in matches)
        except Exception as error:
            errors.append(dict(index=module['index'],filename=module['filename'],error=str(error)))
    monsters = export_table(2363)
    entities = export_table(1955)
    monster_ids = {m['MonsterID'] for r in records for m in r['fields'].get('MonsterInfo',[])}
    selected_monsters = [r for r in monsters['rows'] if r['id'] in monster_ids]
    entity_ids = {r['fields']['ENTITY_ID'] for r in selected_monsters if 'ENTITY_ID' in r['fields']}
    selected_entities = [r for r in entities['rows'] if r['id'] in entity_ids]
    lods, levels = export_table(1268), export_table(6328)
    lod_ids = {r['fields']['LOD_ID'] for r in selected_entities if 'LOD_ID' in r['fields']}
    selected_lods = [r for r in lods['rows'] if r['id'] in lod_ids]
    level_ids = {i for r in selected_lods for i in r['fields'].get('LOD_MODEL_LIST',[])}
    selected_levels = [r for r in levels['rows'] if r['id'] in level_ids]
    availability = []
    for path in sorted({r['fields']['MODEL_PATH'] for r in selected_levels if r['fields'].get('MODEL_PATH')}):
        candidates = [path]
        source = None
        if path.lower().endswith('.gim') and len(lookup_logical(catalogue,path))==1:
            local = OUT.parent/'encounter-models'/(hashlib.sha256(path.encode()).hexdigest()[:20]+'.gim')
            source = extract(apk,catalogue,path,local,APK_SHA256)
            gim = ET.fromstring(local.read_bytes())
            candidates += [gim.attrib.get('Mesh',path[:-4]+'.mesh'),path[:-4]+'.mtg']
            candidates += [e.attrib['value'] for e in gim.findall('GisFiles/*')]
        availability.append(dict(path=path,source=source,resources=[dict(path=p,matches=lookup_logical(catalogue,p)) for p in candidates],
            scope='GIM, explicit Mesh or same-stem mesh candidate when absent, GisFiles, same-stem MTG; textures/shader and decoded animation validity not checked'))
    candidate = next(r for r in records if r['id']==10405)
    candidate_monster = next(r for r in selected_monsters if r['id']==6605)
    skill_ids = {r['SKILL_ID'] for r in candidate_monster['fields']['RANDOM_SKILL_IDS']}
    skills = export_table(9333)
    report = dict(evidence='Hash-verified local static literal joins, not REA or runtime evidence',
        scenes=scenes,scene_source=scene_table['source'],coverage=coverage,errors=errors,
        encounter_sources=sources,encounters=records,monsters=selected_monsters,monster_source=monsters['source'],
        entities=selected_entities,entity_source=entities['source'],apk_sha256=APK_SHA256,
        lods=selected_lods,lod_source=lods['source'],levels=selected_levels,level_source=levels['source'],model_availability=availability,
        reusable_model_candidate=dict(encounter_id=candidate['id'],monster_id=6605,entity_id=6605,
            is_source_test_encounter=True,source_name=candidate['fields']['Name'],
            skills=[r for r in skills['rows'] if r['id'] in skill_ids],skills_source=skills['source'],
            missing_skill_rows=sorted(skill_ids-{r['id'] for r in skills['rows']}),
            limitation='Source test battle, not a recovered campaign level. Same model as tutorial enemy; different skills, buffs and stat scaling.'),
        missing_monster_rows=sorted(monster_ids-{r['id'] for r in selected_monsters}),
        missing_entity_rows=sorted(entity_ids-{r['id'] for r in selected_entities}),
        limitations=['Table metadata/runtime defaults are not evaluated.',
            'Scene XML editor actors are not used as a battle lineup.',
            'SpawnPointIdx/MonsterSpawnIndex runtime selection and level scaling require further tracing.',
            'Model references are not a complete dependency or animation availability check.'])
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(modules=len(modules),parsed=len(coverage),errors=errors,encounters=len(records),monsters=len(selected_monsters),entities=len(selected_entities),model_paths=len(availability),direct_model_dependencies_matched=sum(bool(r['source']) and all(len(p['matches'])==1 for p in r['resources']) for r in availability)),ensure_ascii=False))

if __name__=='__main__':main()
