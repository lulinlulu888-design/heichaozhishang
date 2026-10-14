"""Export static pile providers and card-library presentation without executing APK code."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/piles/providers'


def main():
    index = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    for row in index:
        raw = (ROOT / row['output']).read_bytes()
        if not (b'getPlayerConsumedCardInfo' in raw or b'ViewExhaustedPileInfos' in raw or row['filename'] in (
            'ui\\ui_fight\\CardShowPanel.py', 'ui\\ui_fight\\FightStuffInfoDialog.py')):
            continue
        selected = ()
        if row['filename'] == 'ui\\UIDataSource.py':
            selected = ('getPlayerUnUsedCardInfo', 'getPlayerUsedCardInfo',
                        'getPlayerConsumedCardInfo', 'getPlayerAllCardsByCharId')
        if b'ViewExhaustedPileInfos' in raw and row['index'] != 9555:
            selected = ('ViewDrawPileInfos', 'ViewDiscardPileInfos', 'ViewExhaustedPileInfos')
        report = static.export(row, selected)
        path = OUT / (str(row['index']) + '.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
        methods = [{k: code[k] for k in ('name', 'constant_path', 'names')}
                   for code in report['code_objects']]
        reports.append(dict(source=row, report=str(path.relative_to(ROOT)),
                            report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), methods=methods))
    (OUT / 'index.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), 'utf8')
    providers = json.loads((OUT / '9555.json').read_text('utf8'))
    interface = json.loads((OUT / '4942.json').read_text('utf8'))
    findings = []
    for method, view, zone in (
        ('getPlayerUnUsedCardInfo', 'ViewDrawPileInfos', 'DrawPile'),
        ('getPlayerUsedCardInfo', 'ViewDiscardPileInfos', 'DiscardPile'),
        ('getPlayerConsumedCardInfo', 'ViewExhaustedPileInfos', 'ExhaustedPile'),
    ):
        source = next(code for code in providers['code_objects'] if code['name'] == method)
        getter = next(code for code in interface['code_objects'] if code['name'] == view)
        def anchor(code, operand):
            matches = [ins['offset'] for ins in code['instructions']
                       if ins['opname'] == 'LOAD_ATTR' and ins.get('operand') == operand]
            if len(matches) != 1:
                raise ValueError('Expected one static member reference: ' + operand)
            return matches[0]
        findings.append(dict(provider=method, provider_bytecode_sha256=source['bytecode_sha256'],
                             view=view, view_reference_offset=anchor(source, view),
                             getter_bytecode_sha256=getter['bytecode_sha256'],
                             manager_reference_offset=anchor(getter, '_viewCardPileMgr'),
                             zone=zone, zone_reference_offset=anchor(getter, zone)))
    (OUT / 'pile-mapping.json').write_text(json.dumps(dict(
        evidence_kind='Local static bytecode extraction, not REA runtime Evidence',
        mappings=findings,
        limitations=['Getter-to-zone mapping only; does not recover server-side move rules.',
                     'Partial opcode map retains unknown instructions in exported reports.'],
    ), ensure_ascii=False, indent=2), 'utf8')
    for report in reports:
        print(report['source']['index'], report['source']['filename'])
        print('exported code objects:', len(report['methods']))


if __name__ == '__main__':
    main()
