"""Record hash-checked source hand geometry and single-owner derived examples."""
import json
import math
from pathlib import Path
import inspect_battle_rules as static

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui'


def main():
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    row=next(r for r in index if r['filename']==r'ui\ui_fight\cards\CardTools.py')
    report=static.export(row)
    expected={'_getR':2800.0,'_getThetaMax':3,'_getAlpha':3.6,'_getDBeta':1,'getCardWidth':126,'getCardHeight':166}
    for name,value in expected.items():
        code=next(c for c in report['code_objects'] if c['name']==name)
        if [(i['opname'],i.get('operand')) for i in code['instructions']] != [('LOAD_CONST',value),('RETURN_VALUE',None)]:
            raise ValueError('Source geometry constant changed: '+name)
    (OUT/'card-tools.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    examples=[]
    for count in (1,2,5,6,10):
        beta=math.degrees(math.acos(2710/2800))-1
        step=min(3,beta/(count-1)) if count>1 else 0
        rows=[]
        for i in range(count):
            angle=(i-(count-1)/2)*step
            rows.append(dict(index=i,x=2800*math.sin(math.radians(angle)),
                y=2800*math.cos(math.radians(angle))-2710,source_rotation=angle,creator_rotation=-angle))
        examples.append(dict(count=count,step_degrees=step,cards=rows))
    evidence=dict(source=report['source'],constants=expected,examples=examples,
        derivation='Single nonempty owner group: alphaSum=0; realW=min((count-1)*3,beta); omega=90-realW/2+i*step; x=-R*cos(omega); y=R*sin(omega)-D; rot=omega-90',
        limitations=['Analyst static interpretation, not APK execution', 'Three-owner grouping and selected-card states not ported',
            'Shared-client screen translation is reconstructed; source local coordinates are recorded here without that translation'])
    (OUT/'card-geometry.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print(json.dumps(dict(source_index=row['index'],example_counts=[r['count'] for r in examples])))


if __name__=='__main__':
    main()
