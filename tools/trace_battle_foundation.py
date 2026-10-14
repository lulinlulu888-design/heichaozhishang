"""Recover declared battle constants and player-facing rules, without execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'analysis/battle-foundation'
GUARDS = {
    6221: 'e09e9130987752b7bd2f875e86b620cb6af290cf4fd291be1bd4b932031f2b9f',
    3935: '40f75fce4944c17831d24193c335f63c68b8da5a1d882b57ba0e749f5f76e0b5',
    6593: '689231dc34feb33306bdadfde2fdaad437051d5c31285cfc31d12e53af386b7b',
    4942: 'e2911c234556cc11d601bbe566bad7da58253e91171b05ef6e1930ff2dea07c1',
    5445: '519ec09017d8fabde7098c4c7a1ea27a0eef99633d23a06d08672509b2c4b10f',
}
CONSTANTS = {
    'MAX_DRAW_CARD_NUM_WHEN_ROUND_START': 10,
    'MAX_HAND_PILE_NUM': 10,
    'DRAW_CARD_NUM_PER_ROUND': 6,
    'MAX_SPECIAL_SKILL_ONE_CHAR_ONE_ROUND': 3,
    'DefaultBattleEnergy': 5,
    'DEC_DRAW_CARD_NUM_PER_ROUND_LOST_CHAR': 1,
}
TEXT_KEYS = ['BATTLE_ULT_TIPS', 'CARD_TIPS', 'CHOUPAI',
             'CONSUMED_PILE_INSTRUCTION', 'QIPAI', 'SHUFFLE_CARD_INSTRUCTION']
KEYWORDS = [4, 5, 8, 12, 22, 53, 57, 61, 71]


def write(name, data):
    (OUTPUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    rows = {row['index']: row for row in inventory}
    modules = {}
    for index, digest in GUARDS.items():
        if rows[index]['decoded_sha256'] != digest:
            raise ValueError(f'Unreviewed source revision at {index}')
        modules[index] = static.read_module(rows[index])
    module = modules[6221]
    instructions = list(static.instructions(module))
    declarations = []
    for n, ins in enumerate(instructions):
        if ins['opname'] != 'STORE_NAME' or ins.get('operand') not in CONSTANTS:
            continue
        before = instructions[n - 1]
        name = ins['operand']
        if before['opname'] != 'LOAD_CONST' or type(before.get('operand')) != int or before['operand'] != CONSTANTS[name]:
            raise ValueError(f'Unreviewed declaration syntax/value for {name}')
        declarations.append({'name': name, 'value': before['operand'], 'numeric_type': 'integer',
                             'source': '6221:module', 'offset_start': before['offset'],
                             'offset_end_exclusive': ins['end_exclusive']})
    if len(declarations) != len(CONSTANTS) or len({d['name'] for d in declarations}) != len(CONSTANTS):
        raise ValueError('Missing or repeated declaration')
    symbol_references = []
    for line in (static.SCRIPT / 'symbols.jsonl').read_text('utf8').splitlines():
        row = json.loads(line)
        hits = sorted(set(CONSTANTS).intersection(row['names'] + row['strings']))
        if hits:
            symbol_references.append({'index': row['index'], 'filename': row['filename'], 'names': hits})
    # The common exporter filters raw Python 2 byte-string keys before decoding;
    # select the already decoded string-key rows here without changing it.
    texts = export_table(3935)
    texts['rows'] = [row for row in texts['rows'] if row['id'] in TEXT_KEYS]
    keywords = export_table(6593, KEYWORDS)
    if {r['id'] for r in texts['rows']} != set(TEXT_KEYS) or {r['id'] for r in keywords['rows']} != set(KEYWORDS):
        raise ValueError('Missing selected text rows')
    write('code-text.json', texts)
    write('keywords.json', keywords)
    functions = []
    for index, wanted in [(4942, 'isCanPlayCard'), (5445, 'isCardCardUse')]:
        result = static.export(rows[index], [wanted])
        if len(result['code_objects']) != 1:
            raise ValueError('Selected function is not unique')
        functions.append(result)
    write('availability-functions.json', functions)
    write('rules-evidence.json', {
        'format': 'hczs-battle-foundation-evidence-v1',
        'authority': 'shipped constants/text and static UI consumers; not server runtime observation',
        'constant_module_bytecode_sha256': hashlib.sha256(module['bytecode']).hexdigest(),
        'declarations': declarations,
        'symbol_reference_scope': {'entries': len(inventory), 'references': symbol_references,
                                   'limit': 'Exact names only; indirect/runtime use not excluded.'},
        'text_rules': [
            {'id': 'round-start-draw', 'source': '3935:CHOUPAI', 'meaning': 'Draw hand from draw pile randomly at round start.'},
            {'id': 'round-end-discard', 'source': '3935:QIPAI', 'meaning': 'Move remaining hand to discard at round end; keyword exceptions exist.'},
            {'id': 'recycle-discard', 'source': '3935:SHUFFLE_CARD_INSTRUCTION', 'meaning': 'Shuffle discard back into draw when draw is empty.'},
            {'id': 'exhaust-not-in-normal-refill', 'source': '3935:CONSUMED_PILE_INSTRUCTION; 6593:57',
             'meaning': 'Normal refill does not use exhausted cards; cooldown is a separate return mechanism.'},
            {'id': 'shield-duration', 'source': '6593:5', 'meaning': 'Absorbs damage; clears at next own round start by default.'},
            {'id': 'combo-ultimate', 'source': '3935:BATTLE_ULT_TIPS',
             'meaning': 'Three consecutive character combo points give an ultimate; max three per character per round.'},
        ],
        'ui_availability': {
            '4942:8.38': 'Returns true outside player round; within round energyAll returns true before canNotPlay check, else skips canNotPlay and compares energy <= fei. This is a view-level hint, not server validation.',
            '5445:6.11': 'Auto-fight consumes cardInfo.canUse and rejects IDs in usingCardUUIDs; does not calculate card legality.'},
        'reconstruction_decisions': [
            'Piles use immutable ordered instance IDs and explicit validated recycle permutations; original random generator/draw ordering remains unknown.',
            'Caller supplies effective hand limit and resolved keyword dispositions; no default declared constant is silently treated as runtime initialization.',
            'Removed cards have a distinct local terminal zone, separate from exhausted/cooldown cards.',
            'No keyword combination precedence, cooldown timing, energy deduction, combo reset or buff overrides is inferred from these texts.'
        ],
        'unresolved': ['Server consumers of declared defaults', 'RNG/shuffle/draw implementation and seed',
                       'Ordering of round triggers and keyword conflicts', 'Server validation and authoritative HP/shield settlement'],
    })
    write('module-sources.json', [{**rows[i], 'verified_decoded_sha256': GUARDS[i]} for i in GUARDS])
    print(json.dumps({'constants': len(declarations), 'text_rows': len(texts['rows']),
                      'keyword_rows': len(keywords['rows']), 'ui_functions': len(functions),
                      'output': OUTPUT.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    main()
