"""Export source opening-buff graphs and evaluate a bounded static projection.

This executes analyst code over literal graph data, never original APK code.
"""
import json
from pathlib import Path
from trace_first_encounter import inventory, literal_table
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/city-scenes/opening-buff'


def project(graph, level, physical_defense, magic_defense):
    story = graph['Storyline']; nodes = story['nodeData']; lines = story['lineData']
    allowed = {'StartEvent','GetMonsterLevelNode','OwnerEntityInputParameterNode',
               'IntParameter','CompareNode','GetRpgProps','BuffTargetAddBuff'}
    if any(n['Type'] not in allowed for n in nodes.values()):
        raise ValueError('Unsupported opening graph node')
    starts = [key for key,n in nodes.items() if n['Type']=='StartEvent']
    if len(starts)!=1: raise ValueError('Expected one entry')
    def value(key, port):
        incoming=[e for e in lines if e['endNode']==key and e['endPort']==port]
        if len(incoming)>1: raise ValueError('Ambiguous input')
        if not incoming: return nodes[key]['Data'].get(port)
        edge=incoming[0]; source=nodes[edge['startNode']]; kind=source['Type']
        if kind=='IntParameter': return source['Data']['value']
        if kind=='OwnerEntityInputParameterNode': return 'owner'
        if kind=='GetMonsterLevelNode' and edge['startPort']=='currLevel': return level
        if kind=='GetRpgProps':
            if source['Data']!={'Type':'GetRpgProps','isInit':False,'method':0,'percent':100}:
                raise ValueError('Nonidentity property projection')
            return {'PropAtkDef':physical_defense,'PropMgcDef':magic_defense}[edge['startPort']]
        raise ValueError('Unsupported graph value')
    queue=[starts[0]]; visits=[]; buffs=[]
    while queue:
        key=queue.pop(0)
        if key in visits: raise ValueError('Repeated execution node')
        visits.append(key); node=nodes[key]; kind=node['Type']; port='__out__'
        if kind=='CompareNode':
            x=value(key,'x'); target=value(key,'target')
            port='less' if x<target else 'greater' if x>target else 'equal'
        elif kind=='BuffTargetAddBuff':
            if value(key,'target')!='owner': raise ValueError('Unexpected buff target')
            buffs.append(dict(id=value(key,'buff'),count=node['Data']['num']))
        elif kind not in ('StartEvent','GetMonsterLevelNode','GetRpgProps'):
            raise ValueError('Unsupported execution node')
        queue.extend(e['endNode'] for e in lines if e['startNode']==key and
                     e['startPort']==port and e['endPort']=='__in__')
    return dict(buffs=buffs,visited=visits)


def main():
    OUT.mkdir(parents=True,exist_ok=True); rows=inventory(); graphs={}
    for buff,index in [(89999,7113),(89990,7227),(89991,658)]:
        report=dict(source=rows[index],**static.literal_story_graph(static.read_module(rows[index])))
        (OUT/f'{buff}.graph.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        graphs[buff]=report
    # Preserve precise class paths instead of exporting every method named Start.
    exports=[]
    for index,class_name in [(6221,'RpgBasicProp'),(7693,'BattleAddRpgProp')]:
        module=static.read_module(rows[index])
        candidates=[(path,c) for path,c in static.walk_codes(module) if c['name'].decode()==class_name]
        if len(candidates)!=1: raise ValueError('Class not unique')
        path,_=candidates[0]; export=static.export(rows[index])
        export['code_objects']=[c for c in export['code_objects'] if tuple(c['constant_path'][:len(path)])==path]
        (OUT/f'{class_name}.code.json').write_text(json.dumps(export,ensure_ascii=False,indent=2),'utf8')
        exports.append(export)
    instructions=exports[0]['code_objects'][0]['instructions']; enum={}
    for a,b in zip(instructions,instructions[1:]):
        if a['opname']=='LOAD_CONST' and b['opname']=='STORE_NAME' and type(a.get('operand')) is int:
            enum[a['operand']]=b['operand']
    assert enum[23]=='PropAtkDamageReduce' and enum[24]=='PropMgcDamageReduce'
    module_ops=list(static.instructions(static.read_module(rows[6221])))
    percent_stores=[i for i,op in enumerate(module_ops) if op['opname']=='STORE_NAME' and op.get('operand')=='FloatPercentProp']
    if len(percent_stores)!=1: raise ValueError('Percentage property list not unique')
    end=percent_stores[0]; build=module_ops[end-1]
    if build['opname']!='BUILD_LIST': raise ValueError('Unsupported percentage list constructor')
    constants=module_ops[end-1-build['argument']:end-1]
    if any(op['opname']!='LOAD_CONST' or not isinstance(op.get('operand'),str) for op in constants):
        raise ValueError('Expected literal percentage property names')
    percent_names=[op['operand'] for op in constants]
    assert all(enum[k] in percent_names for k in (23,24))
    map_end=[i for i,op in enumerate(module_ops) if op['opname']=='STORE_NAME' and op.get('operand')=='RpgPropMap']
    if len(map_end)!=1: raise ValueError('Property map not unique')
    end_map=map_end[0]
    start_map=next(i for i in range(end_map-1,-1,-1) if module_ops[i]['opname']=='BUILD_MAP')
    body=module_ops[start_map+1:end_map]; prop_map={}; reverse={name:key for key,name in enum.items()}
    if len(body)%4: raise ValueError('Unexpected map construction')
    for i in range(0,len(body),4):
        a,b,c,d=body[i:i+4]
        if [x['opname'] for x in (a,b,c,d)]!=['LOAD_CONST','LOAD_NAME','LOAD_ATTR','STORE_MAP'] or b.get('operand')!='RpgBasicProp':
            raise ValueError('Nonliteral property mapping')
        key=reverse[c['operand']]
        if key in prop_map: raise ValueError('Duplicate property key')
        prop_map[key]=a['operand']
    assert prop_map[23]=='PropAtkDamageReduce' and prop_map[24]=='PropMgcDamageReduce'
    effects={}
    for buff in (89990,89991):
        nodes=graphs[buff]['graph']['Storyline']['nodeData']
        adds=[n['Data'] for n in nodes.values() if n['Type']=='BattleAddRpgProp']
        if len(adds)!=1: raise ValueError('Expected one property change')
        effects[buff]=dict(**adds[0],property_name=enum[adds[0]['rpgPropType']])
        raw=adds[0]['addValue']; name=prop_map[adds[0]['rpgPropType']]
        if adds[0]['isRatio'] is not False or name not in percent_names: raise ValueError('Unsupported conversion branch')
        effects[buff]['modifier_argument']=dict(value=repr(raw/100.0),hex=(raw/100.0).hex(),
            scope='Start false-isRatio percentage-property branch; not final aggregated property')
    cases=[]
    for level,atk,mgc,expected in [(40,1,1,[]),(240,1,1,[]),(241,1,1,[89990]),
        (241,0,1,[89991]),(241,-1,1,[89991]),(241,0,0,[]),(400,1,0,[89990])]:
        result=project(graphs[89999]['graph'],level,atk,mgc)
        assert [b['id'] for b in result['buffs']]==expected
        cases.append(dict(level=level,physical_defense=atk,magic_defense=mgc,result=result))
    report=dict(evidence='Hash-verified static graph extraction and bounded analyst projection; not original execution or REA evidence',
        buffs=literal_table(391,{89999,89990,89991}),effects=effects,cases=cases,
        percentage_properties=dict(names=percent_names,instructions=module_ops[end-1-build['argument']:end+1],source=rows[6221]),
        property_map=dict(values=prop_map,instructions=module_ops[start_map:end_map+1],source=rows[6221]),
        graph_hashes={key:value['raw_json_sha256'] for key,value in graphs.items()},
        conclusion='level>=241; physical defense>0 selects89990, otherwise magic defense>0 selects89991; at most one selected',
        limits=['Native entity modifier lifetime and original buff event dispatch not executed.',
                'Modifier argument is99/100.0; final aggregation, damage and removal are not established by this projection.',
                'Current local level40 cannot enter the projected level gate; no production buff runtime added.'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(graphs=3,cases=len(cases),effects=effects)))

if __name__=='__main__': main()
