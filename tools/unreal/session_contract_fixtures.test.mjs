import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createBattle, playCard, endTurn, validateState } from '../../packages/battle-session/src/index.js';

test('UE v3 contract fixture replays production reducers with pinned immutable definition and receipts', async () => {
  const fixture = JSON.parse(await readFile(new URL('../../clients/unreal5%205.8/Source/Hczs/Private/Tests/Fixtures/city-ultimate-v3.json', import.meta.url), 'utf8'));
  assert.equal(fixture.fixtureSchemaVersion, 1);
  const definition = fixture.initial.battle.scenario.definition;
  let next = createBattle(definition, 0);
  assert.deepEqual(next.state, fixture.initial.battle.state);
  assert.deepEqual(next.events, fixture.initial.events);
  for (const { command, receipt } of fixture.steps) {
    assert.equal(command.expectedRevision, next.state.actionIndex + 1);
    next = command.type === 'play-card' ? playCard(definition, next.state, command.instanceId) : endTurn(definition, next.state);
    assert.deepEqual(next.state, receipt.battle.state);
    assert.deepEqual(next.events, receipt.events);
    assert.equal(receipt.battle.revision, next.state.actionIndex + 1);
    assert.deepEqual(validateState(definition, receipt.battle.state), next.state);
    assert.equal(receipt.battle.scenario.definition.enemy.id, '6605');
  }
  const generated = fixture.steps.find(step => step.name === 'generated').receipt;
  assert.equal(generated.battle.state.ultimate.generatedTotal, 1);
  const used = fixture.steps.find(step => step.name === 'used').receipt;
  assert.equal(used.battle.state.energy, 0);
  assert.deepEqual(used.battle.state.piles.removed, ['ultimate:1']);
  assert.deepEqual(used.events.filter(event => event.type === 'DamageApplied').map(event => event.amount), ['72', '72', '144', '144', '144', '289', '289', '289']);
});
