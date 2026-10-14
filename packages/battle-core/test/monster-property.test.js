import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { int, float, monsterProperty, toTagged } from '../src/index.js';

const vectors = JSON.parse(await readFile(new URL(
  '../../../analysis/battle-visual/city-scenes/monster-properties/vectors.json', import.meta.url), 'utf8'));
const decode = value => value.kind === 'integer' ? int(value.value) : float(Number(value.value));
for (const [i, row] of vectors.cases.entries()) {
  test(`monster property Python vector ${i}: ${row.label}`, () => {
    const input = row.force === null ? { forced: null, base: decode(row.base),
      monsterRatio: decode(row.ratios[0]), mazeRatio: decode(row.ratios[1]), challengeRatio: decode(row.ratios[2]) }
      : { forced: decode(row.force) };
    const actual = monsterProperty(input), expected = decode(row.expected);
    assert.equal(actual.kind, expected.kind);
    assert.equal(actual.value, expected.value);
    if (actual.kind === 'binary64') assert.equal(toTagged(actual).hex, row.expected.hex);
  });
}
test('monster context must be resolved explicitly; no guessed neutral defaults', () => {
  assert.throws(() => monsterProperty({}), /forced/);
  assert.throws(() => monsterProperty({ forced: null, base: int(500), monsterRatio: float(1) }), /mazeRatio/);
  assert.throws(() => monsterProperty({ forced: 0 }), /scalar/);
});
