// CLI for the new reconstruction API. Runs an owned ephemeral-port service;
// does not stop/restart any existing preview service or launch a game window.
import { parseArgs } from 'node:util';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline/promises';
import assert from 'node:assert/strict';
import { createApp } from '../server/src/app.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const { values } = parseArgs({ options: {
  auto: { type: 'boolean', default: false }, new: { type: 'boolean', default: false },
  'verify-reopen': { type: 'boolean', default: false }, report: { type: 'string' },
  seed: { type: 'string', default: '5000' },
  'custom-scenario': { type: 'string' },
  'save-path': { type: 'string' },
} });
const seed = Number(values.seed);
if (!Number.isSafeInteger(seed) || seed < 0 || seed > 0xffffffff) throw new Error('seed must be uint32');
const options = { port: 0, dataDirectory: resolve(root, 'analysis/game-data'),
  tutorialDirectory: resolve(root, 'analysis/first-encounter'),
  savePath: resolve(values['save-path'] ?? resolve(root, values['custom-scenario'] ? 'runtime/server/custom-cli.sqlite' : 'runtime/server/tutorial-cli.sqlite')),
  customScenarioPath: values['custom-scenario'] ? resolve(values['custom-scenario']) : undefined };
let app = await createApp(options);
let reader;
const log = [];
let reopenVerified = false;
async function api(path, body) {
  const response = await fetch(app.address + '/api/rebuild/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(`${result.error?.code}: ${result.error?.message}`);
  return result;
}
function display(battle) {
  const s = battle.state, d = battle.scenario.definition;
  console.log(`\n回合 ${s.round} | 能量 ${s.energy} | ${d.player.name} HP ${s.player.hp.decimal} 盾 ${s.player.shield.decimal}`);
  console.log(`${d.enemy.name} HP ${s.enemy.hp.decimal} 盾 ${s.enemy.shield.decimal} | ${s.status}`);
  s.piles.hand.forEach((instanceId, i) => {
    const entry = s.cards.find(c => c.instanceId === instanceId), card = d.cards[entry.cardId];
    console.log(`${i + 1}. ${card.name} 费用 ${card.cost} [${instanceId}]`);
  });
}
try {
  const profiles = (await api('/profiles')).profiles;
  const profile = profiles[0] ?? (await api('/profiles', { displayName: '教程旅人' })).profile;
  const base = `/profiles/${profile.id}/battles`;
  const unfinished = values.new ? undefined : (await api(base)).battles.filter(b => b.status === 'player-turn').at(-1);
  let battle = unfinished ? (await api(`${base}/${unfinished.id}`)).battle
    : (await api(base, { requestId: randomUUID(), seed })).battle;
  console.log(battle.scenario.title);
  console.log(battle.scenario.notice);
  console.log(`战斗 ${battle.id}，存档 ${options.savePath}.battles`);
  if (!values.auto) reader = createInterface({ input: process.stdin, output: process.stdout });
  let count = 0;
  while (battle.state.status === 'player-turn') {
    if (++count > 200) throw new Error('CLI action limit reached; saved state remains available');
    display(battle);
    let action;
    if (values.auto) {
      const playable = battle.state.piles.hand.map(instanceId => {
        const c = battle.state.cards.find(c => c.instanceId === instanceId);
        const card = battle.scenario.definition.cards[c.cardId];
        return { instanceId, card, score: card.effects.filter(e => e.type === 'damage').reduce((a, e) => a + Number(e.amount), 0) / Math.max(card.cost, 1) };
      }).filter(c => c.card.cost <= battle.state.energy).sort((a, b) => b.score - a.score);
      action = playable.length ? { type: 'play-card', instanceId: playable[0].instanceId } : { type: 'end-turn' };
    } else {
      const answer = (await reader.question('输入牌序号出牌，e 结束回合，q 保存退出：')).trim();
      if (answer === 'q') break;
      if (answer === 'e') action = { type: 'end-turn' };
      else {
        const index = Number(answer) - 1;
        if (!Number.isInteger(index) || index < 0 || index >= battle.state.piles.hand.length) { console.log('请输入有效序号。'); continue; }
        action = { type: 'play-card', instanceId: battle.state.piles.hand[index] };
      }
    }
    const input = { requestId: randomUUID(), expectedRevision: battle.revision, ...action };
    let result;
    try { result = await api(`${base}/${battle.id}/actions`, input); }
    catch (error) { if (values.auto) throw error; console.log(error.message); continue; }
    battle = result.battle;
    log.push({ command: input, events: result.events, revision: battle.revision });
    if (values['verify-reopen'] && !reopenVerified) {
      // Only this script's own service is closed. The save is read by a new
      // connection after reopening; a separate process check exists in tests.
      await app.close();
      app = await createApp(options);
      const restored = (await api(`${base}/${battle.id}`)).battle;
      assert.deepEqual(restored, battle);
      battle = restored;
      reopenVerified = true;
      console.log('已验证关闭并重新打开服务后，战斗状态一致。');
    }
  }
  console.log(`\n结果：${battle.state.status}，回合 ${battle.state.round}，版本 ${battle.revision}。每一步均已存档。`);
  if (values.report) {
    const target = resolve(values.report);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, JSON.stringify({ kind: 'new-reconstruction-api-cli-run', originalGameFidelityVerified: false,
      nativeClientRuntimeVerified: false, reopenVerified, savePath: options.savePath, battle, log }, null, 2) + '\n');
  }
} finally { reader?.close(); await app.close(); }
