"""Recover literal spawn presets and static selection evidence; no game code execution."""
import json
from pathlib import Path
import inspect_battle_rules as static
from trace_first_encounter import inventory, literal_table
from extract_game_data import plain, export_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/city-scenes/battle-placement'

def literal_assignments(module):
    """Only literal constants, maps, sequences and unique name assignments."""
    stack, assignments = [], {}
    for ins in static.instructions(module):
        op, arg = ins['opcode'], ins['argument']
        if op == 0x99: stack.append(plain(module['consts'][arg]))
        elif op == 0x97: stack.append({})
        elif op == 0x08:
            if len(stack)<3: raise ValueError('Map stack underflow')
            key, value = stack.pop(), stack.pop()
            if not isinstance(stack[-1],dict) or type(key) not in (str,int) or key in stack[-1]:
                raise ValueError('Invalid or duplicate map key')
            stack[-1][key] = value
        elif op in (0x87,0x5a):
            if arg>len(stack): raise ValueError('Sequence stack underflow')
            values=stack[-arg:] if arg else []
            if arg: del stack[-arg:]
            stack.append(values)
        elif op == 0x91:
            name = module['names'][arg].decode('utf8')
            if len(stack)!=1 or name in assignments: raise ValueError('Invalid assignment')
            assignments[name]=stack.pop()
        elif op == 0x53:
            if stack != [None] or ins['end_exclusive'] != len(module['bytecode']): raise ValueError('Invalid module return')
            stack.pop()
        else: raise ValueError(f'Nonliteral opcode {op:#x} at {ins["offset"]}')
    if stack: raise ValueError('Unconsumed literals')
    return assignments

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=inventory()
    preset=literal_assignments(static.read_module(rows[407]))['data']
    sources=[]
    for index,names in ((2471,('getBattleMonsterConfigPosRot','getBattleAllMonsterInfos','sortIndexFunc')),
                        (9330,('getConfigPosRot',)),(9555,('getBattleMonsterConfigPosRot',))):
        result=static.export(rows[index],names)
        (OUT/f'{index}.code.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        sources.append(rows[index])
    battle=literal_table(6500,{10405})
    monster=export_table(2363,{6605})
    entity=export_table(1955,{6605})
    b,m,e=(x['rows'][0]['fields'] for x in (battle,monster,entity))
    spawn=preset[b['MonsterSpawnIndex']][b['MonsterInfo'][0]['SpawnPointIdx']]
    skills=export_table(9333,{s['SKILL_ID'] for s in m['RANDOM_SKILL_IDS']})
    result=dict(evidence='Local hash-verified static parsing and analyst-derived branch result, not runtime evidence',
        preset_source=rows[407],presets=preset,script_sources=sources,battle=battle,monster=monster,entity=entity,skills=skills,
        derived=dict(encounter=10405,scene=b['BattleScene'],spawn_preset=b['MonsterSpawnIndex'],slot=0,
            position=spawn['pos'],rotation_radians=[a+b for a,b in zip(spawn['rot'],e['ROTATION'])],
            entity_base_scale=e['SCALE'],entity_elite_multiplier=e['SCALE_IN_ELITE_BATTLE'],
            conditional_elite_scale=[a*b for a,b in zip(e['SCALE'],e['SCALE_IN_ELITE_BATTLE'])]),
        limitations=['Selection branch assumes received monster slot equals source SpawnPointIdx.',
            'Entity adapter overrides, runtime scene changes and enum selection not executed.',
            'conditional_elite_scale applies only if runtime DifficultyType selects EliteBattle.',
            'Client skill replacement data does not recover server damage/effect execution.'])
    (OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(result['derived']))
    print(json.dumps([dict(id=r['id'],replacement=r['fields'].get('CLIENT_SKILL_REPLACE')) for r in skills['rows']]))

if __name__=='__main__':main()
