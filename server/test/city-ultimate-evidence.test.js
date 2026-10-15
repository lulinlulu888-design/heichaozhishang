import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { ultimateSourceDigest, validateUltimateEvidence } from '../src/city-ultimate.js';

const source = JSON.parse(await readFile(new URL('../../analysis/battle-rules/ultimate-trigger.json', import.meta.url), 'utf8'));

test('ultimate source pin is independent of implementation snapshots, report formatting and property order', () => {
  const expected = validateUltimateEvidence(source);
  const copy = structuredClone(source);
  copy.currentImplementation = [{ file: 'changed-business.js', sha256: '0'.repeat(64) }];
  copy.entryGates.existingCityPreview.currentImplementationReady = true;
  copy.evidenceKind = 'new report annotation';
  copy.tables.elsa_card.source.output = 'another-checkout/decoded.marshal';
  copy.code.points_and_per_round_limit.source.output = 'different-local-output';
  assert.equal(validateUltimateEvidence(copy), expected);
  const reverseKeys = value => Array.isArray(value) ? value.map(reverseKeys) : value && typeof value === 'object' ?
    Object.fromEntries(Object.entries(value).reverse().map(([key, child]) => [key, reverseKeys(child)])) : value;
  assert.equal(validateUltimateEvidence(JSON.parse(JSON.stringify(reverseKeys(copy), null, 4))), expected);
});

test('ultimate source pin rejects altered APK identities, literal fields, instruction bodies and graph defaults', () => {
  for (const mutate of [
    report => { report.tables.elsa_card.source.decoded_sha256 = '0'.repeat(64); },
    report => { report.tables.elsa_card.rows[0].fields.COST = 1; },
    report => { report.tables.states.rows[0].fields.RPG_DEFAULT_FORMULA = '300'; },
    report => { report.tables.courses.rows[0].fields.DisableSpecialSkill = false; },
    report => { report.code.tutorial_gate.code_objects[0].bytecode_sha256 = '0'.repeat(64); },
    report => { report.code.points_and_per_round_limit.code_objects[0].instructions.pop(); },
    report => { report.code.round_limit_literal.instructions[0].operand = 4; },
    report => { report.graphs.energyadd.graph.tamperedParameter = 1; },
    report => { report.reverseIndexes.states.requested['410104'].value.pop(); },
  ]) {
    const copy = structuredClone(source); mutate(copy);
    assert.notEqual(ultimateSourceDigest(copy), ultimateSourceDigest(source));
    assert.throws(() => validateUltimateEvidence(copy), /canonical APK source SHA-256 mismatch/);
  }
});
