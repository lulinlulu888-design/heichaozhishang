"""Recover source BT and linked skill graphs for city test encounter 10405."""
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from trace_first_encounter import inventory, literal_table, extra_index
from inspect_battle_rules import read_module, literal_story_graph
from neox_resource_paths import read_catalogue, lookup
from inspect_neox_model import extract_npk_entry
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-visual/city-scenes/battle-skills'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    monster=literal_table(2363,{6605})
    m=monster['rows'][0]['fields'];path='bt/'+m['BT_PATH']
    with zipfile.ZipFile(apk) as archive: listing=archive.read('assets/assets.list')
    if path not in listing.decode('utf8').splitlines():raise ValueError('Behavior not listed')
    matches=[r for r in lookup(read_catalogue(apk),path) if r['member']=='assets/assets.npk']
    if len(matches)!=1:raise ValueError('Behavior path not unique')
    row=matches[0]
    provenance=extract_npk_entry(apk,row['member'],row['index'],OUT/'M6605.xml')
    provenance.update(logical_path=path,apk_sha256=APK_SHA256,assets_list_sha256=hashlib.sha256(listing).hexdigest())
    xml=ET.fromstring((OUT/'M6605.xml').read_bytes())
    nodes=[dict(e.attrib) for e in xml.iter('Node')]
    ids={int(n['skillID']) for n in nodes if 'skillID' in n}|{r['SKILL_ID'] for r in m['RANDOM_SKILL_IDS']}
    tables={};indexes={}
    for name,index in [('skills',9333),('states',8903),('timelines',6655)]:
        wanted=ids
        if name!='skills':
            idx=extra_index(index,ids);indexes[name]=idx
            if any(v is None for v in idx['requested'].values()):raise ValueError('Skill reverse index absent')
            wanted={i for v in idx['requested'].values() for i in v['value']}
        tables[name]=literal_table(index,wanted)
        if name!='skills':
            by_id={r['id']:r['fields'] for r in tables[name]['rows']}
            if any(by_id[i]['OwnerSkill']!=int(skill) for skill,v in indexes[name]['requested'].items() for i in v['value']):
                raise ValueError('OwnerSkill disagrees with reverse index')
    graph_names={r['fields']['STORYLINE_NAME'] for r in tables['states']['rows']}
    buff_ids={r['fields']['STORYLINE_PARAM']['BUFF_ID'] for r in tables['states']['rows'] if 'BUFF_ID' in r['fields'].get('STORYLINE_PARAM',{})}
    buff_ids.update(r[0] for r in m.get('BATTLE_START_BUFF_LIST',[]))
    tables['buffs']=literal_table(391,buff_ids)
    buff_graph_names={r['fields']['STORYLINE_STORYLINE_NAME'] for r in tables['buffs']['rows']}
    graphs=[]
    for row in inventory().values():
        filename=row['filename'].replace('\\','/')
        basename=filename.rsplit('/',1)[-1][:-3]
        if ('/card_action/server/' in filename and basename in graph_names) or ('/storyline_implement/buff/' in filename and basename in buff_graph_names):
            result=dict(source=row,**literal_story_graph(read_module(row)))
            (OUT/f'graph-{row["index"]}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
            graphs.append(dict(index=row['index'],filename=filename,sha256=result['raw_json_sha256']))
    report=dict(evidence='Static shipped XML and literal graph data; no original AI/runtime execution',
        monster=monster,behavior_source=provenance,behavior_nodes=nodes,skill_ids=sorted(ids),tables=tables,indexes=indexes,graphs=graphs,
        unresolved_graph_names=sorted((graph_names|buff_graph_names)-{g['filename'].rsplit('/',1)[-1][:-3] for g in graphs}),
        limitations=['BT condition/operation implementations and graph execution are not evaluated.',
            'Weights alone do not reproduce original random draws.',
            'Parameter providers, damage/buff semantics and target selection require explicit recovery.'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(skill_ids=sorted(ids),graphs=graphs,missing=report['unresolved_graph_names']),ensure_ascii=False))

if __name__=='__main__':main()
