"""Recover Lynn card joins and shipped graphs without executing game scripts."""
import json
from pathlib import Path
from extract_game_data import export_table
from trace_first_encounter import literal_table, inventory, extra_index
from inspect_battle_rules import read_module, literal_story_graph
from inspect_neox_animation import save_json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/lynn/battle'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    build=export_table(9561)
    selected=[r for r in build['rows'] if r['fields'].get('Character')==2]
    build['rows']=selected
    own=[r for r in selected if r['fields'].get('IsInitialCard') or r['fields'].get('JustShow')]
    items=literal_table(8498,{r['fields']['CardItemID'] for r in own})
    item_by_id={r['id']:r for r in items['rows']}
    cards=export_table(3391,{r['fields']['CARD_ID'] for r in items['rows']})
    card_by_id={r['id']:r for r in cards['rows']}
    skills=export_table(9333,{r['fields']['SKILL_ID'] for r in cards['rows']})
    skill_ids={r['id'] for r in skills['rows']}
    linked={}; indexes={}
    for name,index in [('states',8903),('timelines',6655)]:
        reverse=extra_index(index,skill_ids)
        if any(v is None for v in reverse['requested'].values()):
            raise ValueError('Missing skill reverse index')
        wanted={i for v in reverse['requested'].values() for i in v['value']}
        linked[name]=literal_table(index,wanted); indexes[name]=reverse
        by_id={r['id']:r['fields'] for r in linked[name]['rows']}
        for skill,entry in reverse['requested'].items():
            if any(by_id[i]['OwnerSkill']!=int(skill) for i in entry['value']):
                raise ValueError('Skill owner and reverse index disagree')
    entity=export_table(1955,{11})
    animation_map=[]
    for row in linked['timelines']['rows']:
        for state in row['fields']['DATA'].get('ANIMATION_LIST',[]):
            clip=entity['rows'][0]['fields']['ANIM_STATES_'+state]
            animation_map.append(dict(skill_id=row['fields']['OwnerSkill'],timeline_id=row['id'],state=state,clip=clip))
    rows=inventory();graphs=[];missing=[]
    for skill in skills['rows']:
        suffix='\\card_action\\server\\'+str(skill['id'])+'.py'
        matches=[r for r in rows.values() if r['filename'].endswith(suffix)]
        if not matches:
            missing.append(dict(skill_id=skill['id'],scope='Exact server graph filename absent; aliases and replacement paths unresolved'))
            continue
        if len(matches)!=1:raise ValueError('Ambiguous graph')
        row=matches[0];report=dict(source=row,**literal_story_graph(read_module(row)))
        save_json(OUT/(str(skill['id'])+'.graph.json'),report)
        graphs.append(dict(skill_id=skill['id'],module_index=row['index'],report=str(skill['id'])+'.graph.json'))
    referenced_graphs=[]
    for name in sorted({r['fields']['STORYLINE_NAME'] for r in linked['states']['rows']}):
        matches=[r for r in rows.values() if r['filename'].endswith('\\card_action\\server\\'+name+'.py')]
        if len(matches)!=1:raise ValueError('Referenced state graph missing or ambiguous: '+name)
        row=matches[0];report=dict(source=row,**literal_story_graph(read_module(row)))
        save_json(OUT/(name+'.graph.json'),report)
        referenced_graphs.append(dict(name=name,module_index=row['index'],report=name+'.graph.json'))
    joins=[]
    for slot in own:
        f=slot['fields'];item=item_by_id[f['CardItemID']];card=card_by_id[item['fields']['CARD_ID']]
        joins.append(dict(slot=slot['id'],item_id=item['id'],card_id=card['id'],name=card['fields']['NAME'],
            skill_id=card['fields']['SKILL_ID'],initial=f.get('IsInitialCard',False),display_only=f.get('JustShow',False)))
    report=dict(evidence='Hash-verified local literal extraction; not original runtime',build=build,items=items,cards=cards,
        skills=skills,joins=joins,graphs=graphs,exact_filename_absences=missing,
        linked_tables=linked,reverse_indexes=indexes,entity=entity,animation_map=animation_map,
        referenced_graphs=referenced_graphs,unresolved_referenced_graphs=[],
        limits=['Other challenge slots are not asserted to be initial cards.',
            'Descriptions and formula fields are not executable skill semantics.',
            'State graph references resolved; runtime parameter precedence and target dispatch not executed.',
            'Client animation mapping is static; clips not yet sampled and no multi-target battle implementation.'])
    save_json(OUT/'card-chain.json',report)
    print(json.dumps(dict(joins=joins,referenced_graphs=referenced_graphs,animation_map=animation_map),ensure_ascii=False))

if __name__=='__main__':main()
