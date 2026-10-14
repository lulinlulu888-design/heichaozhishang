import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { int, float, multiply, propertyValue, rpgPropertyPercent, toTagged } from '../src/index.js';

const vectors = JSON.parse(await readFile(new URL(
  '../../../analysis/battle-visual/city-scenes/breakdown-buff/property-vectors.json', import.meta.url), 'utf8'));
const decode = value => value.kind === 'integer' ? int(value.value) : float(Number(value.value));
for (const [i, row] of vectors.cases.entries()) {
  test(`GetRpgProps independent Python vector ${i}`, () => {
    const actual = rpgPropertyPercent({ property: decode(row.property), percent: decode(row.percent), method: row.method });
    const expected = decode(row.expected);
    assert.equal(actual.kind, expected.kind);
    assert.equal(actual.value, expected.value);
    if (actual.kind === 'binary64') assert.equal(toTagged(actual).hex, row.expected.hex);
  });
}

test('breakdown composes current attack modifiers, nonnegative clamp and stack percentage', () => {
  const property = propertyValue({ base: int(101), modifiers: [int(50), int(-10)], isPropAtk: true });
  assert.equal(rpgPropertyPercent({ property, percent: multiply(int(2), int(20)), method: 0 }).value, BigInt(56));
  const depleted = propertyValue({ base: int(101), modifiers: [int(-200)], isPropAtk: true });
  assert.equal(rpgPropertyPercent({ property: depleted, percent: int(40), method: 0 }).value, BigInt(0));
});

test('projection rejects missing or untyped dependencies', () => {
  assert.throws(() => rpgPropertyPercent({ property: int(10), percent: int(20) }), /method/);
  assert.throws(() => rpgPropertyPercent({ property: int(10), percent: int(20), method: 0.5 }), /integer/);
  assert.throws(() => rpgPropertyPercent({ property: 10, percent: int(20), method: 0 }), /scalar/);
});
