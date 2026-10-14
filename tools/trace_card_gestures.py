"""Preserve source gesture branches and current engine end/cancel behavior without execution."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui'


def main():
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    requested={
        r'common\design\DesignConst.py':('getCardOutThreshold_Min','getCardOutThreshold_Max'),
        r'ui\ui_fight\cards\CardBaseArea.py':('_doTouchDown','_doTouchMove','_doTouchUp','_doTouchCancel'),
        r'ui\ui_fight\cards\FightTargetCard.py':('onSelectedOutRelease',),
        r'ui\ui_fight\cards\FightCard.py':('onSelected','onUnSelected'),
    }
    reports=[]
    for name,methods in requested.items():
        row=next(r for r in index if r['filename']==name)
        report=static.export(row,methods)
        if {c['name'] for c in report['code_objects']} != set(methods):
            raise ValueError('Missing source method')
        reports.append(report)
    thresholds=reports[0]['code_objects']
    for code in thresholds:
        expected=5 if code['name'].endswith('_Min') else 30
        if [(i['opname'],i.get('operand')) for i in code['instructions']] != [('LOAD_CONST',expected),('RETURN_VALUE',None)]:
            raise ValueError('Threshold source changed')
    engine=ROOT/'.tools/cocos/3.8.8/resources/resources/3d/engine/cocos/scene-graph/node-event-processor.ts'
    text=engine.read_text('utf8')
    start=text.index('    private _handleTouchEnd (')
    end=text.index('    // #endregion handle touch event',start)
    result=dict(evidence_kind='Hash-verified static APK scripts plus installed Creator engine source; no original runtime execution',
        scripts=reports,engine=dict(path=str(engine),sha256=hashlib.sha256(engine.read_bytes()).hexdigest(),excerpt=text[start:end]),
        findings=['Source press selects the card; source normal release clears selection.',
            'Source upward displacement threshold is 5 or 30 depending on detail-view state.',
            'Source cancel handler releases an out-card only when end y > 100; targeted card then checks CanPlay and target errors.',
            'Creator node touch end outside its hit area is rewritten to TOUCH_CANCEL, also used for actual input cancellation.'],
        next_implementation='Track gestures on the full battle canvas, bind card instance identity at press, distinguish end from cancel, validate drag and target on release.',
        limitations=['Original coordinate adaptation and detailed selection visuals incomplete',
            'No gesture changes applied to current playable preview in this evidence step'])
    (OUT/'card-gesture-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(source_modules=len(reports),methods=sum(len(r['code_objects']) for r in reports))))


if __name__=='__main__':
    main()
