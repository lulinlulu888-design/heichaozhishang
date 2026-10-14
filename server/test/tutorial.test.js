import test from 'node:test';
import assert from 'node:assert/strict';
import { copyFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadTutorialScenario } from '../src/tutorial.js';
import { validateDefinition } from '../../packages/battle-session/src/index.js';

const sourceDirectory = fileURLToPath(new URL('../../analysis/first-encounter/', import.meta.url));
const scenario = await loadTutorialScenario();
const definition = scenario.definition;

async function copyEvidence(t) {
  const directory = await mkdtemp(join(tmpdir(), 'hczs-tutorial-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await Promise.all(Object.keys(scenario.policies.sourcePins).map(file => copyFile(join(sourceDirectory, file), join(directory, file))));
  return directory;
}

test('actual recovered first encounter has five card definitions and seven distinct ordered instances', () => {
  validateDefinition(definition);
  assert.deepEqual(Object.keys(definition.cards), ['110001', '110009', '210003', '410101', '410102']);
  assert.deepEqual(definition.deck.map(item => item.cardId), ['410101', '110001', '210003', '110009', '210003', '110001', '410102']);
  assert.equal(new Set(definition.deck.map(item => item.instanceId)).size, 7);
  assert.deepEqual(scenario.policies.rules.deckEntry.tuple, ['cardId', 'ownerCharacterId']);
  assert.deepEqual(scenario.provenance.deckOwnership.map(item => item.ownerCharacterId), Array(7).fill('1'));
  assert.deepEqual(scenario.provenance.deckOwnership.map(({ instanceId, cardId }) => ({ instanceId, cardId })), definition.deck);
  assert.deepEqual(Object.values(definition.cards).map(item => [item.name, item.cost]),
    [['斩击', 1], ['猛力斩击', 2], ['强力斩击', 1], ['二连斩击', 1], ['疾驰斩击', 2]]);
  assert.deepEqual(definition.enemyIntents, [['990'], ['991'], ['992']]);
  assert.deepEqual(definition.enemyFallback, ['990']);
  assert.deepEqual([definition.initialDraw, definition.roundDraw, definition.energyPerRound, definition.handLimit, definition.maxRounds], [6, 6, 5, 10, 30]);
});

test('binary64 baseline retains the original expression rounding, without decimal-reference substitution', () => {
  assert.deepEqual(definition.player, { id: '1', name: '艾尔莎', maxHp: {
    numeric_type: 'binary64', decimal: '1768.8000000000002', hex: '0x1.ba33333333334p+10',
  } });
  assert.deepEqual(definition.enemy, { id: '991', name: '幻眼魔方', maxHp: { numeric_type: 'integer', decimal: '4600' } });
  assert.equal(scenario.provenance.baseline.calculation.maxHp.exactDecimal, '1768.8');
  assert.equal(scenario.provenance.statsRecovered, false);
  assert.equal(scenario.provenance.baseline.originalFinalCombatStatsRecovered, false);
});

test('known neutral scenario results are produced with binary64 inputs and complete battle-core traces', () => {
  const amounts = Object.fromEntries(Object.entries(definition.cards).map(([id, card]) => [id, card.effects.filter(effect => effect.type === 'damage').map(effect => effect.amount)]));
  assert.deepEqual(amounts, { 110001: ['385'], 110009: ['723'], 210003: ['482'], 410101: ['361', '361'], 410102: ['1447'] });
  assert.equal(scenario.provenance.calculations.length, 9);
  const damage = scenario.provenance.calculations.filter(item => item.function === 'calcDamage');
  for (const calculation of damage) {
    assert.equal(calculation.result.numeric_type, 'integer');
    assert.deepEqual(calculation.trace.map(item => item.stage), ['base_and_add', 'counter', 'defense', 'buff', 'critical',
      'damage_properties', 'overwhelm', 'extra_attack', 'extra_attacked', 'extra_damage', 'clamped']);
    assert.equal(calculation.source.kind, 'reconstruction-resolved-input');
    assert.equal(calculation.source.providerRecovered, false);
    assert.equal(calculation.inputs.rpgAttackType.decimal, '1');
  }
  const slash = damage.find(item => item.stateId === 294);
  assert.deepEqual(slash.source.baseResolution.attack, { numeric_type: 'binary64', decimal: '482.4', hex: '0x1.e266666666666p+8' });
  assert.deepEqual(slash.source.baseResolution.factor, { numeric_type: 'integer', decimal: '80' });
  assert.deepEqual(slash.source.baseResolution.divisor, { numeric_type: 'binary64', decimal: '100.0', hex: '0x1.9000000000000p+6' });
  assert.equal(slash.trace.at(-1).value.numeric_type, 'binary64');
  assert.equal(slash.result.decimal, '385');
  for (const [id, expected] of [['990', '302'], ['991', '402']]) {
    const calculation = damage.find(item => item.source.skillId === id);
    assert.equal(calculation.inputs.rpgBasicActionValue.decimal, '0');
    assert.equal(calculation.inputs.extraDamage.decimal, expected);
    assert.equal(calculation.trace.find(item => item.stage === 'extra_damage').value.decimal, expected);
    assert.deepEqual(definition.enemySkills[id].effects, [{ type: 'damage', target: 'opponent', amount: expected }]);
  }
});

test('shield goes through calcBlock with explicit neutral source, target and null card', () => {
  const shield = scenario.provenance.calculations.find(item => item.function === 'calcBlock');
  assert.equal(shield.stateId, 4);
  assert.equal(shield.inputs.card, null);
  assert.equal(shield.inputs.basicBlock.decimal, '300');
  assert.equal(shield.source.baseResolution.missingRpgBase.decimal, '0');
  assert.deepEqual(shield.inputs.source, { propAddTargetShield: { numeric_type: 'integer', decimal: '0' }, shieldFactor: { numeric_type: 'integer', decimal: '0' } });
  assert.deepEqual(shield.trace.map(item => item.stage), ['base', 'source_property', 'target_property', 'shield_factors', 'additional_block', 'clamped']);
  assert.equal(shield.result.decimal, '300');
  assert.deepEqual(definition.enemySkills['992'].effects, [{ type: 'shield', target: 'self', amount: '300' }]);
});

test('card/state conflicts remain client-visible alongside explicit policy selections', () => {
  assert.deepEqual(scenario.provenance.conflicts.map(item => [item.cardId, item.stateId, item.cardValue, item.originalStateValue, item.selectedValue]),
    [['110009', 296, 150, '80', 150], ['410102', 368, 300, '200', 300], ['410102', 367, 0, 1, 0]]);
  assert.deepEqual(definition.cards['410102'].effects[1], { type: 'draw', count: 0 });
  assert.match(scenario.notice, /OwnerIndex.*新设计/);
  assert.match(scenario.notice, /VALUE=0.*VALUE=1/);
  assert.match(scenario.notice, /未恢复.*中性/);
  assert.equal(scenario.policies.rules.playerBaseDamage.providerRecovered, false);
  assert.equal(scenario.policies.rules.monsterMissingRpgBase.originalMissingFieldBehaviorRecovered, false);
});

test('evidence projections include verified original module hashes, rows and field locations', () => {
  const cards = scenario.provenance.tables['player-cards.json'];
  assert.equal(cards.source.index, 3391);
  assert.equal(cards.source.decoded_sha256, 'c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09');
  assert.equal(cards.rows.find(row => row.id === 110001).fields.RPG_DEFAULT_FORMULA[0][0], 80);
  assert.ok(cards.rows.find(row => row.id === 110001).fieldSources.RPG_DEFAULT_FORMULA.bytecode_start > 0);
  assert.equal(scenario.provenance.formulaSource.moduleIndex, 7042);
  assert.match(scenario.provenance.codeHashes['../../packages/battle-core/src/index.js'], /^[a-f0-9]{64}$/);
});

test('copied pinned evidence has the same rule/evidence identity and JSON-safe client response', async t => {
  const directory = await copyEvidence(t);
  const copy = await loadTutorialScenario(directory);
  assert.equal(copy.definition.id, definition.id);
  assert.equal(copy.definition.id, `tutorial-5000-${copy.provenance.ruleEvidenceHash}`);
  assert.deepEqual(JSON.parse(JSON.stringify(copy)), copy);
  assert.ok(Object.isFrozen(copy.definition.cards['410101'].effects));
});

test('missing mandatory source fails closed', async t => {
  const directory = await copyEvidence(t);
  await rm(join(directory, 'player-baseline.evidence.json'));
  await assert.rejects(loadTutorialScenario(directory), /required source player-baseline.evidence.json unavailable/);
});

test('forged source module, row, field, position and rounded HP are rejected without fallback', async t => {
  const directory = await copyEvidence(t);
  const mutations = [
    ['player-cards.json', data => { data.source.decoded_sha256 = '0'.repeat(64); }],
    ['player-cards.json', data => { data.rows[0].id = 999; }],
    ['player-cards.json', data => { data.rows[0].fields.RPG_DEFAULT_FORMULA = [[999]]; }],
    ['player-cards.json', data => { delete data.rows[0].field_sources.RPG_DEFAULT_FORMULA; }],
    ['player-baseline.json', data => { data.baseStatsTagged.maxHp.decimal = '1768'; }],
    ['player-baseline.json', data => { delete data.baseStatsTagged; }],
    ['skill-states.json', data => { data.rows.find(row => row.id === 367).fields.STORYLINE_PARAM.VALUE = 0; }],
  ];
  for (const [file, mutate] of mutations) {
    const raw = await readFile(join(sourceDirectory, file));
    const data = JSON.parse(raw);
    mutate(data);
    await writeFile(join(directory, file), JSON.stringify(data));
    await assert.rejects(loadTutorialScenario(directory), /SHA-256 mismatch/);
    await writeFile(join(directory, file), raw);
  }
});
