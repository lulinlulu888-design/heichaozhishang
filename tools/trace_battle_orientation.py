"""Recover source player rotation without executing shipped Python code."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/battle-orientation'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    row = next(r for r in rows if r['index'] == 8067)
    report = static.export(row, ('__init__', 'updateUserData'))
    # Scope to BattlePlayerEntity, avoiding same-named methods in other classes.
    module = static.read_module(row)
    selected = []
    for entry in report['code_objects']:
        obj = module
        parents = []
        for index in entry['constant_path']:
            parents.append(obj['name'].decode('utf8'))
            obj = obj['consts'][index]
        if 'BattlePlayerEntity' in parents:
            entry['parents'] = parents
            selected.append(entry)
    if len(selected) != 2:
        raise ValueError('Player entity methods changed')
    report['code_objects'] = selected
    path = OUT/'player-rotation-script.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    table = export_table(1955, {0})
    entity = next(r for r in table['rows'] if r['id'] == 0)
    rotation = entity['fields']['ROTATION']
    if rotation != [0.0, 1.5708, 0.0]:
        raise ValueError('Expected source player rotation changed')
    data = dict(entityId=0, rotationEulerRadians=rotation,
        source=table['source'], sourceRow=entity,
        scriptReportSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scope='Static player default rotation; rotOffset defaults to None. Native Euler convention and all conditional offsets not runtime-verified.')
    (OUT/'player-orientation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')
    scene = export_table(9650, {2081})
    (OUT/'original-battle-scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(entityId=0, rotationEulerRadians=rotation)))

if __name__ == '__main__':
    main()
