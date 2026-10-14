"""Export hash-verified original EndArea state handlers without executing them."""
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'


def main():
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    requests = [
        (4589, ('_onRefreshHandcardUsability','_onAniBlackInEnd','_onAniWhiteInEnd',
                '_onAniBlackOutEnd','_onAniWhiteOutEnd'), 'end-turn-completion-evidence.json'),
        (8266, ('_initAutoWidgets',), 'end-turn-widget-evidence.json'),
        (8266, ('switchStateTo_enemyturn','switchStateTo_myturn'), 'end-turn-state-evidence.json'),
        (4589, ('_changeRoundState','_switchTo','_setBtnShow','_setBtnTouch',
                '_refreshNonCardCanUseState'), 'end-turn-control-evidence.json'),
    ]
    for number, methods, filename in requests:
        report = static.export(next(row for row in index if row['index'] == number), methods)
        if set(methods) != {code['name'] for code in report['code_objects']}:
            raise ValueError('Requested EndArea handlers changed')
        (OUT/filename).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(exports=len(requests), source='Hash-verified local static scripts; no original execution')))


if __name__ == '__main__':
    main()
