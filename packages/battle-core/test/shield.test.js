import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { calcBlock, int as I, float as F, fromTagged, toTagged } from '../src/index.js';

const vectors = JSON.parse(await readFile(new URL('../../../analysis/shield-formula/scalar-vectors.json', import.meta.url), 'utf8'));
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
assert.equal(vectors.source_module_sha256, 'ea9b0bb6c277d605e039bbbc6e18d4eabad98fb8316659948129efa4709586fc');
assert.equal(vectors.calcBlock_bytecode_sha256, '7ecf0058ee6a29019274c7f081a666765fa4a11d936e0803099ad4ad6eefaaee');
for (const vector of vectors.cases) {
  test(`calcBlock Python reference: ${vector.name}`, () => {
    const actual = calcBlock(decode(vector.inputs)), expected = decode(vector.expected), trace = decode(vector.trace);
    equalScalar(actual.block, expected);
    assert.deepEqual(actual.trace.map(x => x.stage), trace.map(x => x.stage));
    actual.trace.forEach((x, i) => equalScalar(x.value, trace[i].value));
    assert.ok(Object.isFrozen(actual) && Object.isFrozen(actual.trace));
    assert.ok(actual.trace.every(Object.isFrozen));
  });
}
const basic = () => ({ basicBlock: I(300), source: null, card: null,
  target: { propBeAddShield: I(0), shieldFactor: I(0), isPVP: false } });
test('calcBlock requires every active dependency and an actual target', () => {
  for (const key of ['basicBlock', 'source', 'card', 'target']) {
    const p = basic(); delete p[key];
    assert.throws(() => calcBlock(p), new RegExp(key));
  }
  for (const key of ['propBeAddShield', 'shieldFactor', 'isPVP']) {
    const p = basic(); delete p.target[key];
    assert.throws(() => calcBlock(p), new RegExp(key));
  }
  assert.throws(() => calcBlock({ ...basic(), target: null }), /target/);
  assert.throws(() => calcBlock({ ...basic(), source: false }), /source/);
  assert.throws(() => calcBlock({ ...basic(), card: [] }), /card/);
  assert.throws(() => calcBlock({ ...basic(), basicBlock: 300 }), /scalar/);
  const p = basic(); p.target.isPVP = true;
  assert.throws(() => calcBlock(p), /pvpShieldRatio/);
  p.target.isPVP = 1;
  assert.throws(() => calcBlock(p), /boolean/);
});
test('shipped three-argument helper call never reads card improvement', () => {
  const p = basic();
  p.source = { propAddTargetShield: I(0), shieldFactor: I(0) };
  equalScalar(calcBlock(p).block, I(300));
  p.card = { extraBaseBlockPercent: I(0), additionalBlockValue: I(0) };
  Object.defineProperty(p.source, 'improvement', { get() { throw new Error('must not read improvement'); } });
  equalScalar(calcBlock(p).block, I(300));
  for (const key of ['propAddTargetShield', 'shieldFactor']) {
    const q = { ...p, source: { ...p.source } }; delete q.source[key];
    assert.throws(() => calcBlock(q), new RegExp(key));
  }
  for (const key of ['extraBaseBlockPercent', 'additionalBlockValue']) {
    const q = { ...p, card: { ...p.card } }; delete q.card[key];
    assert.throws(() => calcBlock(q), new RegExp(key));
  }
});
test('zero clamp uses integer first operand and successful calls do not mutate input', () => {
  const p = basic(); p.basicBlock = F(-0);
  Object.freeze(p.target); Object.freeze(p);
  const r = calcBlock(p);
  equalScalar(r.trace.at(-1).value, I(0));
  equalScalar(r.block, I(0));
  assert.ok(Object.is(p.basicBlock.value, -0));
});
