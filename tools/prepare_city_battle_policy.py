"""Pin recovered city evidence for an explicitly configured local battle."""
import hashlib
import json
from pathlib import Path
from trace_city_monster_properties import main as properties
from trace_city_battle_skills import main as skills

ROOT = Path(__file__).resolve().parents[1]

def main():
    properties()
    skills()
    pins = {}
    for name in ('monster-properties', 'battle-skills'):
        path = ROOT/f'analysis/battle-visual/city-scenes/{name}/report.json'
        pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    policy = dict(format='hczs-city-preview-v1', encounter=10405, monster=6605, level=40,
        sourcePins=pins, maxRounds=30,
        assumptions=[
            'Level40 is an explicit local preview setting, not a recovered challenge level.',
            'Player baseline/cards/deck and neutral damage/shield modifiers reuse the existing tutorial reconstruction.',
            'Maze and challenge multipliers are explicitly neutral; opening buff89999 and defenses/counters are not implemented.',
            'Single-opponent target substitution; source area attack does not imply multi-target support.',
            'Every third round starting at1 uses66054; other rounds use source weights with local SHA256 seeded selection, not the original RNG.',
            'Breakdown uses existing breakdown-reconstruction-v1 semantics, not original event dispatch.'
        ])
    dest = ROOT/'server/data/city-preview-policy.json'
    dest.write_text(json.dumps(policy, ensure_ascii=False, indent=2), 'utf8')
    print(dest)

if __name__ == '__main__':
    main()
