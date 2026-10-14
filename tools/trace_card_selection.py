"""Record original selection behavior without assuming a generic card-lift animation."""
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/card-selection-evidence.json'


def main():
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    requested={
        6992:('onSelected','onUnSelected','setZOrder','onOtherSelected','_onCardDrag'),
        356:('onSelected','update'),
        3273:('selectCard','reArrangeCards','_checkMovePosition'),
        222:('_onChoiceOneCard','_onGiveUpChoiceOneCard'),
        9485:('EffectSelect','play','stop','_showSelectEffect','_removeSelectEffect'),
    }
    scripts=[]
    for number,methods in requested.items():
        report=static.export(next(row for row in index if row['index']==number),methods)
        if number==9485:
            # Method names play/stop occur in several unrelated effect classes.
            report['code_objects']=[c for c in report['code_objects'] if
                c['constant_path'][:1]==[33] or c['name'] in ('_showSelectEffect','_removeSelectEffect')]
            if not {'EffectSelect','play','stop'} <= {c['name'] for c in report['code_objects']}:
                raise ValueError('EffectSelect class path changed')
        scripts.append(report)
    result=dict(evidence_kind='Hash-verified local static scripts, no original execution',scripts=scripts,
        findings=[
            'FightCard.onSelected copies normal position to touch position, enters Select effect, and changes to STAGE_TOUCHED.',
            'setZOrder uses 200 for selected cards and supplied order for others.',
            'TargetCard.update seeks touch position before dragging out; after out it emits arrow and seeks normal position.',
            'EffectSelect reads style-dependent color pairs S11/S12 etc., colors eight sprites, and loops animation in; stop hides and pauses it.',
            'OwnCardArea selection changes energy preview and toggles battle_screen_01 visibility.',
            'The inspected handlers do not establish a universal fixed selected-card lift or scale multiplier.'
        ],next_steps=['Recover the EffectSelect layout/timeline and texture paths.',
                      'Trace detailed card preview separately from hand-card transforms.'],
        limitations=['No selected visuals added to playable client in this step.',
                     'Negative observation is limited to these methods; other controls/timelines may alter transforms.'])
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(modules=len(scripts),methods=sum(len(r['code_objects']) for r in scripts),output=str(OUT))))


if __name__=='__main__':
    main()
