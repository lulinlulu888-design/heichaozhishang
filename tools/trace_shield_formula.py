"""Hash-guarded calcBlock evidence and synthetic Python reference vectors.

The reference below is an analyst-written translation, not executed APK code.
All divisors in this function are binary64, so Python 3 follows the recovered
Python 2 arithmetic here; int() truncates and max() retains its first tie.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/shield-formula'
MODULE_SHA = 'ea9b0bb6c277d605e039bbbc6e18d4eabad98fb8316659948129efa4709586fc'
FUNCTION_SHAS = {
    (10,): '33f24a5a9e7685a2f87bda23c7068cd55fa3b14d73c8b3af49de0930ad32efe6',
    (11,): '7ecf0058ee6a29019274c7f081a666765fa4a11d936e0803099ad4ad6eefaaee',
}


def tagged(value):
    if value is None or type(value) is bool or type(value) is str:
        return value
    if type(value) is int:
        return {'numeric_type': 'integer', 'decimal': str(value)}
    if type(value) is float:
        return {'numeric_type': 'binary64', 'decimal': repr(value), 'hex': value.hex()}
    if isinstance(value, list):
        return [tagged(v) for v in value]
    if isinstance(value, dict):
        return {k: tagged(v) for k, v in value.items()}
    raise TypeError(type(value))


def basic_action_reference(basic_value, src, strength_factor=None, card=None):
    # Exact recovered positional signature. strength_factor is unused.
    if card is not None and src is not None:
        improvement = src['improvement']
        if improvement is not None:
            basic_value += improvement['factor'] * improvement['property'] + improvement['base']
    return basic_value


def reference(p):
    src, dst, card = p['source'], p['target'], p['card']
    value = p['basicBlock']
    trace = []
    def stage(name, value):
        trace.append({'stage': name, 'value': value})
    if src is not None:
        # The shipped call passes only THREE arguments; card binds to the
        # unused strength_factor slot. The fourth slot retains default None.
        value = basic_action_reference(value, src, card)
    stage('base', value)
    if src is not None:
        value *= 1 + src['propAddTargetShield'] / 1000.0
        stage('source_property', value)
    value *= 1 + dst['propBeAddShield'] / 1000.0
    stage('target_property', value)
    dst_factor = dst['shieldFactor']
    src_factor = src['shieldFactor'] if src is not None else 0
    value *= 1 + src_factor + dst_factor + (card['extraBaseBlockPercent'] / 100.0 if card is not None else 0)
    stage('shield_factors', value)
    value += card['additionalBlockValue'] if card is not None else 0
    stage('additional_block', value)
    if dst['isPVP']:
        value *= dst['pvpShieldRatio']
        stage('pvp', value)
    value = max(0, value)
    stage('clamped', value)
    return int(value), trace


def cases():
    base = {'basicBlock': 300, 'source': None, 'card': None,
            'target': {'propBeAddShield': 0, 'shieldFactor': 0, 'isPVP': False}}
    out = []
    def add(name, p):
        result, trace = reference(p)
        out.append({'name': name, 'inputs': tagged(p), 'expected': tagged(result), 'trace': tagged(trace)})
    add('explicit-neutral-target-no-source-no-card', base)
    for name, value in [('fractional', 300.999), ('negative', -1), ('negative-zero', -0.0),
                        ('subnormal', float.fromhex('0x0.0000000000001p-1022')),
                        ('large-integer-before-target-float', 9007199254740993)]:
        p = copy.deepcopy(base); p['basicBlock'] = value; add(name, p)
    p = copy.deepcopy(base)
    p['source'] = {'propAddTargetShield': 250, 'shieldFactor': 0.2}
    add('source-without-card-needs-no-improvement', p)
    p['card'] = {'extraBaseBlockPercent': 30, 'additionalBlockValue': 11}
    add('card-present-helper-card-argument-still-none', p)
    p['source']['improvement'] = {'factor': 0.75, 'property': 17, 'base': -2}
    p['target']['propBeAddShield'] = 125
    p['target']['shieldFactor'] = -0.1
    add('all-dependencies-with-unbound-improvement-ignored', p)
    p['target'].update(isPVP=True, pvpShieldRatio=0.67)
    add('pvp-last-before-clamp', p)
    p = copy.deepcopy(base)
    p['card'] = {'extraBaseBlockPercent': 20, 'additionalBlockValue': 1}
    add('card-without-source', p)
    for name, prop in [('property-cancels', -1000), ('property-reverses', -1500)]:
        p = copy.deepcopy(base); p['target']['propBeAddShield'] = prop; add(name, p)
    p = copy.deepcopy(base)
    p['target'].update(isPVP=True, pvpShieldRatio=0.0)
    add('zero-pvp-clamp-type', p)
    p = copy.deepcopy(base)
    p['basicBlock'] = 1
    p['source'] = {'propAddTargetShield': 0, 'shieldFactor': 1e16, 'improvement': None}
    p['target']['shieldFactor'] = -1e16
    p['card'] = {'extraBaseBlockPercent': 100, 'additionalBlockValue': 0}
    add('left-associative-factor-sum', p)
    p = copy.deepcopy(base)
    p['card'] = {'extraBaseBlockPercent': -200, 'additionalBlockValue': 350}
    add('additional-can-recover-negative-intermediate', p)
    p = copy.deepcopy(base)
    p['basicBlock'] = 10
    p['target']['propBeAddShield'] = 333
    p['target'].update(isPVP=True, pvpShieldRatio=0.75)
    add('truncate-only-at-end', p)
    return out


def main():
    rows = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    row = next(row for row in rows if row['index'] == 7042)
    if row['decoded_sha256'] != MODULE_SHA:
        raise ValueError('unreviewed formula module')
    exported = static.export(row, ['<module>', '_calcRpgBasicActionValue', 'calcBlock'])
    if len(exported['code_objects']) != 3:
        raise ValueError('unexpected function selection')
    for code in exported['code_objects']:
        if code['constant_path'] == []:
            defaults = [i for i in code['instructions'] if 0x6a <= i['offset'] < 0x79]
            expected = [('LOAD_CONST', None), ('LOAD_CONST', None),
                        ('LOAD_CONST', {'code_name': '_calcRpgBasicActionValue'}),
                        ('MAKE_FUNCTION', 2), ('STORE_NAME', '_calcRpgBasicActionValue')]
            if [(i['opname'], i.get('operand', i['argument'])) for i in defaults] != expected:
                raise ValueError('unreviewed helper defaults/binding')
            continue
        if FUNCTION_SHAS.get(tuple(code['constant_path'])) != code['bytecode_sha256']:
            raise ValueError('unreviewed formula bytecode')
        if any(i['opname'] == 'UNKNOWN' for i in code['instructions']):
            raise ValueError('unmapped selected opcode')
    OUT.mkdir(parents=True, exist_ok=True)
    def write(name, data):
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf8')
    write('function-sources.json', exported)
    vectors = cases()
    write('scalar-vectors.json', {
        'kind': 'synthetic Python translation; no APK runtime execution',
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_module_sha256': MODULE_SHA,
        'calcBlock_bytecode_sha256': FUNCTION_SHAS[(11,)],
        'binding': 'calcBlock passes three args to a four-argument helper; cardObj stays default None, so no improvement is applied',
        'cases': vectors,
    })
    print(json.dumps({'output': str(OUT), 'source_functions': 2, 'synthetic_vectors': len(vectors)}))


if __name__ == '__main__':
    main()
