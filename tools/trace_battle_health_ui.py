"""Recover source health layouts; static evidence, not original runtime behavior."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from inspect_battle_ui_layout import Reader
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/health'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK differs')
    catalogue = read_catalogue(apk)
    index = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    OUT.mkdir(parents=True, exist_ok=True)
    layouts = []
    for name in ('PlayerHeadArea', 'MonsterHeadArea', 'BossHeadArea', 'HpShieldArea', 'FightMainPanel'):
        filename = f'ui_auto\\uires_FightPanel_FightNewPanel_{name}.py'
        row = next(r for r in index if r['filename'] == filename)
        module = static.read_module(row)
        paths = [c.decode('utf8') for c in module['consts'] if isinstance(c, bytes) and c.endswith(b'.csb')]
        if len(paths) != 1:
            raise ValueError('Expected unique CSB')
        path = OUT / (name + '.csb')
        provenance = extract(apk, catalogue, paths[0], path, APK_SHA256)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != provenance['sha256']:
            raise ValueError('CSB hash mismatch')
        reader = Reader(data)
        root = reader.scalar('I', 0)
        version = reader.string(reader.field(root, 0))
        if version != '2.1.0.0':
            raise ValueError('Unsupported CSB version')
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        layouts.append(dict(name=name, module_source=row, source=provenance, tree=tree))
        methods = ('_initAutoWidgets', 'switchStateTo_alive', 'switchStateTo_dead') if name in (
            'PlayerHeadArea', 'MonsterHeadArea', 'BossHeadArea') else ('_initAutoWidgets',)
        evidence = static.export(row, methods)
        (OUT / (name + '-widgets.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), 'utf8')
    runtime_row = next(r for r in index if r['filename'] == 'ui\\ui_fight\\PlayerHeadArea.py')
    runtime = static.export(runtime_row, ('initComponents', '_canUseBossHead', 'getHeadAreaPos',
        'addPlayerHeadArea', '_initPlayerHeads', 'addBossHeadArea', 'getMonstHeadArea', 'refreshHeadShow',
        'onUpdateDead', 'showKilled', 'refreshHpShow'))
    (OUT / 'runtime-placement.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), 'utf8')
    for label, filename in (
        ('player-head-data', 'ui\\ui_data\\FightDataTools.py'),
        ('player-head-data-entry', 'ui\\UIDataSource.py'),
    ):
        row = next(r for r in index if r['filename'] == filename)
        evidence = static.export(row, ('getBattlePlayerHeadInfos',))
        (OUT / (label + '.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), 'utf8')
    row = next(r for r in index if r['filename'] == 'ui\\ui_data\\CharDataTools.py')
    evidence = static.export(row, ('<module>', 'getCharacterHomeBattleChessData', '<lambda>'))
    evidence['code_objects'] = [c for c in evidence['code_objects']
        if c['name'] != '<lambda>' or c['constant_path'] in ([168], [541])]
    (OUT / 'player-battle-icon-binding.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), 'utf8')
    report = dict(apk_sha256=APK_SHA256, layouts=layouts,
        evidence_kind='Hash-checked extraction and bounded local static CSB/marshal parsers; not REA runtime evidence',
        limitations=['Source-local geometry only; runtime slot assignment not fully reconstructed',
            'Visibility, action timelines, runtime scaling and health interpolation not executed',
            'Partial CSB field reader; not a full FlatBuffers verifier'])
    (OUT / 'layouts.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(layouts=len(layouts), output=str(OUT)), ensure_ascii=False))


if __name__ == '__main__':
    main()
