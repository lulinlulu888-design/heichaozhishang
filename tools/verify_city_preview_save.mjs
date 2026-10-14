// Read-only verification of the latest completed local city preview.
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { validateState, createBattle, playCard, endTurn } from '../packages/battle-session/src/index.js';
import { weightedIntents } from '../server/src/weighted-intents.js';
const weighted = process.argv.includes('--weighted');
const savePath = new URL('../runtime/server/city-preview.sqlite.battles', import.meta.url);
const db = new DatabaseSync(savePath, { readOnly: true });
let report;
try {
  const rows = db.prepare('SELECT * FROM battles ORDER BY created_at DESC, id DESC').all();
  const row = rows.find(r => {
    const scenario = JSON.parse(r.scenario_json);
    return scenario.provenance?.mode === 'city-reconstruction-preview' &&
      Boolean(scenario.provenance?.enemySelection) === weighted && JSON.parse(r.state_json).status === 'won';
  });
  assert.ok(row, 'status preview battle exists');
  assert.equal(createHash('sha256').update(row.scenario_json).digest('hex'), row.scenario_hash);
  const scenario = JSON.parse(row.scenario_json), state = validateState(scenario.definition, JSON.parse(row.state_json));
  assert.equal(state.format, 'hczs-battle-session-v2'); assert.equal(state.status, 'won');
  const receipts = db.prepare('SELECT request_json,result_json FROM battle_commands WHERE battle_id=?').all(row.id)
    .map(r => ({ request: JSON.parse(r.request_json), result: JSON.parse(r.result_json) }))
    .sort((a,b) => a.result.battle.revision - b.result.battle.revision);
  assert.equal(receipts.length, row.revision - 1);
  for (let i = 0; i < receipts.length; ++i) assert.equal(receipts[i].result.battle.revision, i + 2);
  const last = receipts.at(-1);
  assert.deepEqual(last.result.battle.state, state); assert.equal(last.request.type, 'play-card');
  const hit = last.result.events.findLast(e => e.type === 'DamageApplied');
  assert.equal(hit.target, 'enemy'); assert.equal(Number(hit.finalHp.decimal), 0);
  if (weighted) {
    const selection = scenario.provenance.enemySelection;
    assert.deepEqual(scenario.definition.enemyIntents,
      weightedIntents(scenario.policies.enemySelection, selection.seed, scenario.definition.maxRounds));
    let replay = createBattle(scenario.definition, selection.seed);
    for (const receipt of receipts) {
      replay = receipt.request.type === 'play-card'
        ? playCard(scenario.definition, replay.state, receipt.request.instanceId)
        : endTurn(scenario.definition, replay.state);
      assert.deepEqual(replay.state, receipt.result.battle.state);
      assert.deepEqual(replay.events, receipt.result.events);
    }
    assert.deepEqual(replay.state, state);
  } else assert.equal(state.round, 3);
  assert.ok(last.result.events.some(e => e.type === 'BattleEnded' && e.status === 'won'));
  report = { evidence: 'Independent read-only SQLite verification of manually played Web preview',
    originalGameFidelityVerified: false, nativeRuntimeVerified: false,
    battleId: row.id, scenarioHash: row.scenario_hash, revision: row.revision,
    weightedSelection: scenario.provenance.enemySelection ?? null, fullCommandReplayVerified: weighted,
    commandCount: receipts.length, state, finalCommand: last.request,
    finalEvents: last.result.events, verifiedAt: new Date().toISOString() };
} finally { db.close(); }
const out = new URL('../analysis/battle-visual/city-scenes/', import.meta.url);
await mkdir(out, { recursive: true });
await writeFile(new URL(weighted ? 'weighted-victory-save-evidence.json' : 'city-victory-save-evidence.json', out), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ revision: report.revision, commands: report.commandCount,
  round: report.state.round, playerHp: report.state.player.hp, stacks: report.state.breakdown, status: report.state.status }));
