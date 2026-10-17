import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { copyFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPrologueBossScenario } from '../src/prologue-boss.js';
import { createBattle, playCard, endTurn } from '../../packages/battle-session/src/index.js';

const directory = fileURLToPath(new URL('../../analysis/prologue-boss/', import.meta.url));
const source = { skip: !existsSync(join(directory, 'party-baseline.json')) && 'Run tools/trace_party_baseline.py against the pinned APK' };

test('battle 1703 uses the source party, owned 14-card deck and boss skills under labelled rules', source, async () => {
  const { definition: d, provenance, policies } = await loadPrologueBossScenario();
  assert.deepEqual(d.party.map(m => [m.id, m.name, m.maxHp.decimal, m.attack.decimal]),
    [['1', '艾尔莎', '1768.8000000000002', '482.4'], ['3', '未来', '2010.0', '402.0']]);
  assert.deepEqual([d.enemy.id, d.enemy.name, d.enemy.maxHp.decimal, d.enemy.attack.decimal], ['2013', '终焉使者', '10000', '180.0']);
  assert.equal(d.deck.length, 14);
  assert.deepEqual(d.deck.map(c => c.ownerId).join(''), '31131311133111');
  assert.deepEqual(d.cards['140004'].effects, [{ type: 'shield', target: 'party', factor: 300 }]);
  assert.deepEqual(d.cards['440303'].effects, [{ type: 'attackBuff', target: 'party', stacks: 1 }]);
  assert.deepEqual(d.enemySkills['74503'].effects, [{ type: 'damage', target: 'first-mid-last', factor: 80, times: 3 }]);
  assert.deepEqual(d.enemySkills['74501'].effects, [{ type: 'attackBuff', target: 'self', stacks: 5 }]);
  assert.deepEqual(d.enemyIntents.slice(0, 4).flat(), ['74503', '74501', '74502', '74503']);
  assert.equal(d.maxRounds, 30);
  assert.equal(provenance.targetResolverRecovered, false);
  assert.equal(policies.rules.targetEnums.resolverRecovered, false);
  assert.ok(provenance.conflicts.some(c => c.cardId === '140004' && c.originalStateValue === '100'));
});

test('a deterministic scripted run reaches a won state with source boss damage values', source, async () => {
  const { definition: d } = await loadPrologueBossScenario();
  let { state } = createBattle(d, 7);
  const bossHits = [];
  while (state.status === 'player-turn') {
    const playable = state.piles.hand.find(id => d.cards[state.cards.find(c => c.instanceId === id).cardId].cost <= state.energy);
    if (playable) { state = playCard(d, state, playable).state; continue; }
    const result = endTurn(d, state);
    bossHits.push(...result.events.filter(e => e.type === 'DamageApplied' && e.actor === 'enemy').map(e => e.amount));
    state = result.state;
  }
  assert.deepEqual([state.status, state.outcomeReason, state.round], ['won', 'enemy-defeated', 5]);
  // 180 * 80% = 144 per firework hit; after five stacks 288 * 1.3 = 374 and 144 * 1.3 = 187.
  assert.deepEqual(bossHits, ['144', '144', '144', '374', '187', '187', '187']);
});

test('modified boss evidence is rejected before a definition is built', source, async t => {
  const copy = await mkdtemp(join(tmpdir(), 'hczs-boss-'));
  t.after(() => rm(copy, { recursive: true, force: true }));
  const { policies } = await loadPrologueBossScenario();
  await Promise.all(Object.keys(policies.sourcePins).map(file => copyFile(join(directory, file), join(copy, file))));
  await loadPrologueBossScenario(copy);
  const raw = await readFile(join(copy, 'monster.json'));
  await writeFile(join(copy, 'monster.json'), Buffer.concat([raw, Buffer.from(' ')]));
  await assert.rejects(() => loadPrologueBossScenario(copy), /SHA-256 mismatch/);
});
