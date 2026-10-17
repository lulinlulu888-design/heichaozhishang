// Writes the UE party-contract fixture from the production reducers and the
// pinned prologue boss evidence. Run from the repository root with node.
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { loadPrologueBossScenario } from '../../server/src/prologue-boss.js';
import { createBattle, playCard, endTurn } from '../../packages/battle-session/src/index.js';

const output = new URL('../../clients/unreal5%205.8/Source/Hczs/Private/Tests/Fixtures/prologue-boss-party-v1.json', import.meta.url);
const { definition, title, notice } = await loadPrologueBossScenario();
const scenario = { title, notice, encounterId: 'prologue-boss-1703', definition };
const wrap = (result, revision) => ({
  battle: { id: '22222222-2222-2222-2222-222222222222', profileId: '11111111-1111-1111-1111-111111111111',
    revision, scenario, state: result.state, createdAt: 100, updatedAt: 100 + revision },
  events: result.events, replayed: false });

function run(choose) {
  let next = createBattle(definition, 7);
  const initial = wrap(next, 1), steps = [];
  while (next.state.status === 'player-turn') {
    const instanceId = choose(next.state);
    const command = { requestId: `step-${steps.length + 1}`, expectedRevision: next.state.actionIndex + 1,
      type: instanceId ? 'play-card' : 'end-turn', ...(instanceId ? { instanceId } : {}) };
    next = instanceId ? playCard(definition, next.state, instanceId) : endTurn(definition, next.state);
    steps.push({ name: command.requestId, command, receipt: wrap(next, next.state.actionIndex + 1) });
  }
  return { initial, steps };
}
const cardOf = (state, id) => definition.cards[state.cards.find(card => card.instanceId === id).cardId];
const win = run(state => state.piles.hand.find(id => cardOf(state, id).cost <= state.energy));
const loss = run(() => null);
const fixture = {
  fixtureSchemaVersion: 1,
  origin: 'Offline production battle-session party reducers with pinned prologue boss evidence; seed 7; no live account or database',
  definitionSha256: createHash('sha256').update(JSON.stringify(definition)).digest('hex'),
  initial: win.initial, steps: win.steps, lossSteps: loss.steps };
await writeFile(output, JSON.stringify(fixture) + '\n');
console.log(`win steps ${win.steps.length} (${win.steps.at(-1).receipt.battle.state.status}); loss steps ${loss.steps.length} (${loss.steps.at(-1).receipt.battle.state.outcomeReason})`);
