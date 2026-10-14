"""Recover PVE player formation without executing shipped game code."""
import json
from pathlib import Path
import inspect_battle_rules as static
from trace_first_encounter import inventory
from extract_game_data import export_table
from trace_city_battle_placement import literal_assignments

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/city-scenes/player-placement'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = inventory()
    offsets = literal_assignments(static.read_module(rows[9442]))
    scene = export_table(9650, {2077})
    entity = export_table(1955, {0})
    base = scene['rows'][0]['fields']['PlayerPosition']
    actor = entity['rows'][0]['fields']
    sources = []
    for index, names in (
        (8874, ('getConfigPosRot',)), (5485, ('SceneTableData',)),
        (2697, ('createBattleEntity', 'addBattleEntity')),
        (9560, ('addPlayerEntity',)), (8067, ('updateUserData',))):
        exported = static.export(rows[index], names)
        (OUT/f'{index}.code.json').write_text(json.dumps(exported, ensure_ascii=False, indent=2), 'utf8')
        sources.append(rows[index])
    slots = [dict(pos_index=i, position=[a+b for a,b in zip(base, delta)],
        rotation_radians=[a+b for a,b in zip(actor['ROTATION'], offsets['rotData'][i])],
        base_scale=actor['SCALE']) for i,delta in enumerate(offsets['posData'])]
    result = dict(evidence='Local hash-verified static parsing; not REA or runtime evidence',
        encounter=10405, scene=scene, example_entity=entity, offsets=offsets,
        offset_source=rows[9442], script_sources=sources, derived_slots=slots,
        branch_notes=[
            'CAvatarChar reads SceneTableData.PlayerPosition and PlayerOrientation.',
            'BattleScene.addPlayerEntity indexes posData/rotData with received posIndex.',
            'BattleModelEntity initializes position from configPosition.',
            'BattlePlayerEntity overwrites rotation with EntityData.ROTATION then adds rotOffset; position adds posOffset.',
            'BossBattle scale multiplier is conditional; Elsa entity 0 has identity multiplier.'],
        limitations=[
            'Slots are alternatives for Elsa, not evidence for three Elsa characters in the original lineup.',
            'Network posIndex assignment, camera runtime changes, focus and swapped positions are not executed.',
            'Scene2077 has no literal PlayerOrientation; no scene orientation is invented.',
            'Monster offset module9150 has duplicate key2003 and is rejected by the strict literal parser; its runtime map is not claimed recovered.'])
    (OUT/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(slots))


if __name__ == '__main__':
    main()
