import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import * as battle from '../src/index.js';

const { int: I, float: F, fromTagged, toTagged } = battle;
const evidence = new URL('../../../analysis/battle-parameters/', import.meta.url);
const load = async name => JSON.parse(await readFile(new URL(name, evidence), 'utf8'));
const vectors = await load('scalar-vectors.json');
function decode(value) {
  if (value && value.numeric_type) return fromTagged(value);
  if (Array.isArray(value)) return value.map(decode);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, decode(v)]));
  return value;
}
function equalScalar(actual, expected) {
  assert.equal(actual.kind, expected.kind);
  assert.equal(actual.value, expected.value);
  if (actual.kind === 'binary64') assert.equal(toTagged(actual).hex, toTagged(expected).hex);
}
const baseline = decode(vectors.cases.find(c => c.kind === 'resolved_damage').inputs);

for (const [index, fixture] of vectors.cases.entries()) {
  test(`Python source vector ${index}: ${fixture.kind}`, () => {
    const p = decode(fixture.inputs), expected = decode(fixture.expected);
    switch (fixture.kind) {
      case 'resolved_damage': {
        const actual = battle.calcDamage(p);
        equalScalar(actual.damage, expected);
        const trace = decode(fixture.trace);
        assert.deepEqual(actual.trace.map(r => r.stage), trace.map(r => r.stage));
        actual.trace.forEach((r, i) => equalScalar(r.value, trace[i].value));
        break;
      }
      case 'missing_required_dependency': {
        const p = { ...baseline };
        delete p[fixture.field];
        assert.throws(() => battle.calcDamage(p), new RegExp(fixture.field));
        break;
      }
      case 'classic_division': equalScalar(battle.classicDivide(...p), expected); break;
      case 'overwhelm': equalScalar(battle.overwhelmRatio({ srcIsPlayer: p[0], dstIsPlayer: p[1], lvDiff: p[2], disabled: p[3] }), expected); break;
      case 'counter': equalScalar(battle.counterRatio({ srcType: p[0], dstType: p[1], allCounter: p[2], allRatio: p[3], table: battle.RECOVERED_COUNTER_TABLE }), expected); break;
      case 'critical_outcome_with_supplied_draw': {
        const actual = battle.criticalOutcome({ srcCritical: p[0], defendCritical: p[1], blockProperty: p[2], draw: p[3], srcCriticalDamage: p[4], cardExtra: p[5], blockDamageProperty: p[6] });
        equalScalar(actual.kind, expected[0]); equalScalar(actual.ratio, expected[1]); break;
      }
      default: assert.fail(`unhandled reference vector ${fixture.kind}`);
    }
  });
}

test('bundled counter fields exactly match the recovered seven original rows', async () => {
  const original = await load('counter-types.json');
  assert.equal(original.source.decoded_sha256, '0fcde2fd8710b3e9617b1805ef4f1c74c8e155ecd21690a1f6dd622cd584874d');
  assert.deepEqual(Object.keys(battle.RECOVERED_COUNTER_TABLE), original.rows.map(row => String(row.id)));
  for (const row of original.rows) {
    const copy = battle.RECOVERED_COUNTER_TABLE[row.id];
    for (const name of ['beCounterID', 'counterID', 'beCounterRatio', 'counterRatio']) {
      if (Object.hasOwn(row.fields, name)) equalScalar(copy[name], name.endsWith('Ratio') ? F(row.fields[name]) : I(row.fields[name]));
      else assert.equal(Object.hasOwn(copy, name), false);
    }
  }
  // Rows 5/6 match both branches: the second IF must win.
  equalScalar(battle.counterRatio({ srcType: I(5), dstType: I(6), allCounter: false, table: battle.RECOVERED_COUNTER_TABLE }), F(1.2));
});

test('required active damage dependencies are never filled with neutral values', () => {
  for (const key of Object.keys(baseline).filter(k => !k.startsWith('propMgc'))) {
    const p = { ...baseline };
    delete p[key];
    assert.throws(() => battle.calcDamage(p), new RegExp(key));
  }
  assert.throws(() => battle.calcDamage({ ...baseline, isPVP: true }), /pvpAtkRatio/);
  assert.throws(() => battle.calcDamage({ ...baseline, isDamageSkillPreview: true }), /slowHp/);
  assert.throws(() => battle.calcDamage({ ...baseline, rpgBasicActionValue: 100 }), /scalar/);
  assert.throws(() => battle.calcDamage({ ...baseline, dstIsPlayer: 1 }), /boolean/);
});

test('real damage skips only its proved branches and requires its remaining dependencies', () => {
  const p = { ...baseline, rpgAttackType: I(3) };
  for (const key of ['combatCounterRatioValue', 'dstEntityDefenseValue', 'attackFactorValue', 'attackedFactorValue', 'criticalRatioValue', 'dstIsPlayer', 'propAtkDamageIncValue', 'propAtkDamageReduceValue', 'propMgcDamageIncValue', 'propMgcDamageReduceValue']) delete p[key];
  equalScalar(battle.calcDamage(p).damage, I(100));
  delete p.overwhelmRatio;
  assert.throws(() => battle.calcDamage(p), /overwhelmRatio/);
});

test('exact integer arithmetic and comparisons never round through Number', () => {
  const large = I('9007199254740993');
  equalScalar(battle.add(large, I(1)), I('9007199254740994'));
  equalScalar(battle.multiply(large, large), I('81129638414606699710187514626049'));
  assert.equal(battle.compare(large, F(9007199254740992)), 1);
  assert.throws(() => I(9007199254740992), /safe integer/);
  for (const [a, b, result] of [[-7, 3, -3], [7, -3, -3], [-7, -3, 2]]) equalScalar(battle.classicDivide(I(a), I(b)), I(result));
  equalScalar(battle.truncate(F(-1.9)), I(-1));
  assert.throws(() => battle.classicDivide(I(1), I(0)), /zero/);
  assert.throws(() => battle.classicDivide(I(1), F(-0)), /zero/);
  assert.throws(() => battle.add(I('1' + '0'.repeat(400)), F(1)), /finite/);
});

test('tagged binary64 preserves signed zero, subnormals and rejects inconsistent hex', () => {
  for (const value of [-0, 0, Number.MIN_VALUE, -Number.MIN_VALUE, Number.MAX_VALUE, 100, 1 - .9]) {
    const encoded = toTagged(F(value));
    equalScalar(fromTagged(JSON.parse(JSON.stringify(encoded))), F(value));
  }
  assert.deepEqual(toTagged(F(Number.MIN_VALUE)), { numeric_type: 'binary64', decimal: '5e-324', hex: '0x0.0000000000001p-1022' });
  assert.throws(() => fromTagged({ numeric_type: 'binary64', decimal: '0.1', hex: '0x0.0p+0' }), /disagree/);
  assert.throws(() => fromTagged({ numeric_type: 'integer', decimal: 100 }), /string/);
  assert.throws(() => F(Infinity), /finite/);
  assert.throws(() => F(NaN), /finite/);
});

test('defense preserves Python 2 int division and explicit zero-attack early exit', () => {
  equalScalar(battle.defenseRatio({ attack: F(100), defense: F(20), penetration: F(0) }), F(.5));
  equalScalar(battle.defenseRatio({ attack: I(100), defense: I(20), penetration: I(0) }), I(0));
  equalScalar(battle.defenseRatio({ attack: F(100), defense: F(20), penetration: F(25) }), F(1));
  equalScalar(battle.defenseRatio({ attack: F(0) }), I(0));
  assert.throws(() => battle.defenseRatio({ attack: I(10), defense: I(20) }), /penetration/);
});

test('resolved helpers retain intermediate truncation, units and collection order', () => {
  equalScalar(battle.basicActionValue({ basicDamage: I(100), improvement: null }), I(100));
  equalScalar(battle.basicActionValue({ basicDamage: I(100), improvement: { factor: F(.5), property: I(3), base: I(2) } }), F(103.5));
  equalScalar(battle.addAttackValue({ rpgBasicActionValue: I(-3), extraBaseDamagePercent: I(50), cardAdditionalValue: I(0), entityAttackAddValue: I(0) }), I(-1));
  equalScalar(battle.attackFactorValue({ factors: [], commonFactors: [F(1.5)], cardFactor: I(0), battleFactor: I(0) }), F(.5));
  equalScalar(battle.attackedFactorValue({ factors: [], commonFactors: [I(50)], excluded: false, reduceDamagedRate: I(25) }), F(.25));
  equalScalar(battle.propertyValue({ base: F(1e16), modifiers: [F(-1e16), I(1)], isPropAtk: false }), F(1));
  equalScalar(battle.propertyValue({ base: F(1e16), modifiers: [I(1), F(-1e16)], isPropAtk: false }), F(0));
  equalScalar(battle.propertyValue({ base: I(-1), modifiers: [], isPropAtk: true }), I(0));
  equalScalar(battle.propertyValue({ base: F(0), modifiers: [], isPropAtk: true }), I(0));
  equalScalar(battle.propertyValue({ base: F(-0), modifiers: [], isPropAtk: true }), I(0));
  assert.throws(() => battle.basicActionValue({ basicDamage: I(100) }), /improvement/);
  assert.throws(() => battle.attackedFactorValue({ factors: [], commonFactors: [], excluded: false }), /reduceDamagedRate/);
  assert.throws(() => battle.attackFactorValue({ factors: [], commonFactors: [], cardFactor: I(0) }), /battleFactor/);
});

test('unsupported client runtime fails explicitly instead of falling back to Number', async () => {
  const source = (await readFile(new URL('../src/numeric.js', import.meta.url), 'utf8')).replace(/^export /gm, '');
  const context = vm.createContext({ BigInt: undefined });
  assert.throws(() => vm.runInContext(source + '\nint("9007199254740993");', context), /requires native BigInt/);
});

test('all runtime modules are ESM with no Node APIs or BigInt literal syntax', async () => {
  for (const name of ['index.js', 'numeric.js', 'tables.js']) {
    const source = await readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(?:require\s*\(|process\.|Buffer\.|node:)/);
    assert.doesNotMatch(source, /\b(?:0[xob][0-9a-f]+|[0-9]+)n\b/i);
  }
});
