// Read-only verification of the latest completed local status preview.
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { validateState } from '../packages/battle-session/src/index.js';
const savePath = new URL('../runtime/server/breakdown-preview.sqlite.battles', import.meta.url);
const db = new DatabaseSync(savePath, { readOnly: true });
let report;
try {
  const rows = db.prepare('SELECT * FROM battles ORDER BY created_at DESC, id DESC').all();
  const row = rows.find(r => JSON.parse(r.scenario_json).policies?.configuration?.id === 'breakdown-trial');
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
  assert.deepEqual(last.result.battle.state, state); assert.equal(last.request.type, 'end-turn');
  const tick = last.result.events.findLast(e => e.type === 'BreakdownTriggered');
  const hit = last.result.events.findLast(e => e.type === 'DamageApplied');
  assert.equal(tick.target, 'enemy'); assert.equal(hit.target, 'enemy');
  assert.equal(hit.amount, tick.amount); assert.equal(hit.finalHp.decimal, '0');
  assert.ok(last.result.events.some(e => e.type === 'BattleEnded' && e.status === 'won'));
  report = { evidence: 'Independent read-only SQLite verification of manually played Web preview',
    originalGameFidelityVerified: false, nativeRuntimeVerified: false,
    battleId: row.id, scenarioHash: row.scenario_hash, revision: row.revision,
    commandCount: receipts.length, state, finalCommand: last.request,
    finalEvents: last.result.events, verifiedAt: new Date().toISOString() };
} finally { db.close(); }
const out = new URL('../analysis/test/status-client/', import.meta.url);
await mkdir(out, { recursive: true });
await writeFile(new URL('victory-save-evidence.json', out), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ revision: report.revision, commands: report.commandCount,
  round: report.state.round, playerHp: report.state.player.hp, stacks: report.state.breakdown, status: report.state.status }));
