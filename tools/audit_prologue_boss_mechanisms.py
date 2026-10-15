"""Focused static mechanism evidence for challenge 3998, never APK execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from extract_texture_samples import APK_SHA256
from inspect_battle_rules import export, read_module, literal_story_graph
from trace_first_encounter import inventory, literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/prologue-boss/mechanism-audit'


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n','utf8')


def main():
    rows=inventory()
    tables={}
    selections={'challenge':(5921,{3998}),'battle':(5766,{1703}),'monster':(2363,{2013}),
                'course':(4105,{2}),'enemySkills':(9333,{74501,74502,74503}),
                'states':(8903,{268,269,270}),'timelines':(6655,{2755,2756,2757,2758}),
                'buff':(391,{1001})}
    for name,(idx,ids) in selections.items():
        tables[name]=literal_table(idx,ids)
        save(name+'.json',tables[name])
    def citation(name,row_id,field=None):
        t=tables[name];r=next(r for r in t['rows'] if r['id']==row_id)
        return {'moduleIndex':t['source']['index'],'filename':t['source']['filename'],
                'decodedSha256':t['source']['decoded_sha256'],'rowId':row_id,
                'location':r['field_sources'][field] if field else r['source']}

    bt=ROOT/'analysis/prologue-boss/boss.xml'
    prov=json.loads(Path(str(bt)+'.provenance.json').read_text('utf8'))
    if prov['apk_sha256']!=APK_SHA256 or hashlib.sha256(bt.read_bytes()).hexdigest()!=prov['sha256']:
        raise ValueError('Prior original BT extraction changed')
    btroot=ET.fromstring(bt.read_bytes())
    operations=sorted({n.get('Operation') for n in btroot.iter() if n.get('Operation')})
    allowed=['PlayerRoundStart','RoundComparison','RoundEnd','RoundMod','SelfRoundStart','ShowSkillIntentions','UseIntentionSkill']
    if operations!=allowed:raise ValueError('Reviewed tutorial BT operations changed')
    btlines=[{'line':i,'xml':line.strip()} for i,line in enumerate(bt.read_text('utf8').splitlines(),1) if 'Operation=' in line]
    save('bt-evidence.json',{'provenance':prov,'operations':operations,'lines':btlines})

    code_selections={3609:{(24,10),(24,11),(24,12),(24,14)},
                     8067:{(20,16),(20,17)},5549:{()},9458:{(21,0)}}
    codes={}
    for idx,paths in code_selections.items():
        e=export(rows[idx]);e['code_objects']=[c for c in e['code_objects'] if tuple(c['constant_path']) in paths]
        if {tuple(c['constant_path']) for c in e['code_objects']}!=paths:raise ValueError('Selected function changed')
        codes[idx]=e;save(f'code-{idx}.json',e)
    def code_ref(idx,path,offsets):
        c=next(c for c in codes[idx]['code_objects'] if c['constant_path']==list(path))
        return {'moduleIndex':idx,'filename':rows[idx]['filename'],'decodedSha256':rows[idx]['decoded_sha256'],
                'constantPath':list(path),'function':c['name'],'bytecodeSha256':c['bytecode_sha256'],
                'instructions':[i for i in c['instructions'] if i['offset'] in offsets]}
    graph=literal_story_graph(read_module(rows[255]))
    save('mainline-graph.json',{'source':rows[255],**graph})
    avg=[]
    for idx in [9251,6977]:
        t=literal_table(idx,None)
        t['rows']=[r for r in t['rows'] if r['fields'].get('DialogID') in [134,138,139]]
        avg.append(t);save(f'avg-{idx}.json',t)
    # Scan every decoded script once, verify each searched byte sequence first.
    # Absence is deliberately narrow and never substitutes for server evidence.
    terms=['TransformMusic','FirstBossTransform','ForceFail','ForceWin']
    search={term:[] for term in terms}
    for row in rows.values():
        raw=(ROOT/row['output']).read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if sha!=row.get('decoded_sha256',row.get('payload_sha256')):raise ValueError('Search source changed')
        for term in terms:
            if term.encode() in raw:search[term].append({'index':row['index'],'filename':row['filename'],'sha256':sha})
    save('bounded-symbol-search.json',{'searchedModules':len(rows),'search':search,
          'scope':'Exact byte strings in decoded scripts only; original server/native/runtime generated names excluded.'})
    report={
      'schemaVersion':1,'apkSha256':APK_SHA256,
      'evidenceKind':'ordinary hash-verified static extraction and analyst interpretation; no original runtime',
      'identity':{'challengeId':3998,'battleId':1703,'monsterId':2013,'entityId':2003,
                  'battleCitation':citation('battle',1703),'monsterCitation':citation('monster',2013)},
      'phaseAndFailure':{
        'verifiedBT':'First round 74503, second round 74501, later odd rounds 74502 and even rounds 74503. Self turn uses the announced intention then ends.',
        'btOperations':operations,'btSource':prov,
        'forcedLossEvidence':'No HP/transform/kill/force-result operation exists in this selected BT; no such field occurs in battle1703 row. This does not prove absent original-server special handling.',
        'roundLimit':{'field':'MaxRoundFail','value':30,'source':citation('battle',1703,'MaxRoundFail'),
                      'interpretation':'Failure limit configuration, not a scripted-defeat proof; exact original server boundary not executed.'},
        'transformMusic':{'value':'FirstBossTransform','source':citation('battle',1703,'TransformMusic'),
                         'consumer':code_ref(8067,(20,16),[9,15,51,72,87]),
                         'meaning':'setTransform truthy state selects music. No battle1703 phase trigger is established by this field.'},
        'transformedNames':{'consumer':code_ref(8067,(20,17),[93,96,99,167,170,173,174]),
                            'map':code_ref(5549,(),[6,12,19,23]),
                            'meaning':'Entity2003 is absent from ChangeAnimMapData overrides, so transformed non-TRANSFORM clips receive _change suffix.',
                            'resourceCaveat':'Literal skill_5_2 is absent, skill_5_2_change exists; not a proven broken or missing phase asset.'},
        'implementationDecision':'Implement the verified tutorial BT and ordinary win/loss. Do not add a forced defeat or second HP bar without a source trigger.'},
      'skills':[
        {'id':74501,'stateId':268,'operation':'SelfAddBuff','buffId':1001,'count':5,
         'source':citation('states',268),'buffSource':citation('buff',1001),
         'animation':'muoumaxituan_skill_4','note':'Buff declares attack ratio 0.06/stack. Preserve actual buff rules; not a transform skill.'},
        {'id':74502,'stateId':269,'operation':'MonsterCauseDamage','times':1,'rpgDefaultFormula':'160','rpgFormula':'PropAtk',
         'targetType':9,'source':citation('states',269),'animation':'muoumaxituan_skill_3',
         'blink':{'hide1':1.1,'show1':1.9,'hide2':3.2,'show2':4.0,'source':citation('timelines',2757)}},
        {'id':74503,'stateId':270,'operation':'MonsterCauseDamage','times':3,'rpgDefaultFormula':'80','rpgFormula':'PropAtk',
         'targetType':9,'source':citation('states',270),'animation':'muoumaxituan_skill_2',
         'note':'Three logical damage applications are configured, but the clip has one attack event. Do not invent three evenly spaced hit timestamps.'}],
      'story':{
        'challengeParameters':{'a':138,'b':134,'source':citation('challenge',3998,'MainlineSLParams')},
        'graphSource':{'moduleIndex':255,'filename':rows[255]['filename'],'decodedSha256':rows[255]['decoded_sha256'],
                       'constantIndex':graph['constant_index'],'loadOffset':graph['load_offset'],'rawJsonSha256':graph['raw_json_sha256']},
        'graphFlow':['AVG138','EnterBattleNode','AVG134','GetCharacterNode(charItemID=1058)','EndEvent'],
        'battleResultConsumer':code_ref(3609,(24,10),[6,12,187,190,241,244,278,281,306,320,323,348]),
        'loseConsumer':code_ref(3609,(24,11),[6,9,31,116,214,248,257]),
        'winConsumer':code_ref(3609,(24,12),[6,9,45,48]),
        'meaning':'EnterBattle branches on returned isWin. Win waits for battleComplete then returns; loss offers restart or leaves storyline. Client-visible source does not equate story catastrophe with a forced combat-loss result.',
        'avg139':'Contains won?/low-HP/black-white-UV presentation entries, but its trigger for 1703 is unproven. Retain as a candidate, not mandatory battle logic.'},
      'minimumPlayableGaps':[
        'Create authoritative two-character party Elsa1/Future3 level100 and the source ordered owner-specific 14-card pile; preserve round2 special-energy gate.',
        'Resolve and test targetType9 selection, three-hit application and buff1001; add source BT intentions 74501/2/3 with stable repeatable authority.',
        'Convert/import actual muoumaxituan geometry, bind pose, source clips and distinct texture colour spaces; no cube substitution.',
        'Rebuild boss_theatre camera/objects from original scene; port emission and alpha states, direct scene SFX and attack effects.',
        'Drive hit and blink presentation from source AGS/timeline evidence while server result and damage stay authoritative.',
        'Play verified before/after story and persist challenge3998 completion exactly once; no invented HasLoot=false rewards.',
        'Phase trigger, AVG139 insertion and original-server result generation remain explicit unresolved items, not silently guessed.'
      ]}
    save('report.json',report)
    print(json.dumps({'path':str(OUT/'report.json'),'searchedModules':len(rows),'btOperations':operations,
                      'phaseTriggerEstablished':False,'forcedLossEstablished':False},ensure_ascii=False))


if __name__=='__main__':main()
