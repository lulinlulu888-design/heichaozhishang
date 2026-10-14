import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadTutorialScenario } from '../src/tutorial.js';
import { loadCustomScenario } from '../src/custom-scenario.js';
import { createApp } from '../src/app.js';
import { fixture, request } from './helpers.js';

const tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url));
const source = new URL('../data/custom/guard-and-draw.json', import.meta.url);
const bytes = await readFile(source);
const base = await loadTutorialScenario(tutorialDirectory);
test('v2 custom status scenario is served over HTTP, heals and resumes without duplicate decrement', async t => {
  const files = await fixture(t);
  const customScenarioPath = join(files.directory, 'status.json');
  const config = JSON.parse(await readFile(new URL('../data/custom/breakdown-trial.json', import.meta.url), 'utf8'));
  await writeFile(customScenarioPath, JSON.stringify(config));
  const options = { ...files, customScenarioPath, tutorialDirectory, port: 0 };
  let app = await createApp(options); files.cleanupWith(() => app.close());
  const profile = (await request(app.address, '/profiles', 'POST', { displayName: '状态试玩验证' })).body.profile;
  const prefix = `/profiles/${profile.id}/battles`;
  const created = await request(app.address, prefix, 'POST', { requestId: 'create', seed: 1 });
  assert.equal(created.status, 201);
  const id = created.body.battle.id, actionPath = `${prefix}/${id}/actions`;
  const inflicted = await request(app.address, actionPath, 'POST', { requestId: 'end', expectedRevision: 1, type: 'end-turn' });
  assert.equal(inflicted.status, 200);
  assert.equal(inflicted.body.battle.state.format, 'hczs-battle-session-v2');
  assert.equal(inflicted.body.battle.state.breakdown.player, 2);
  const command = { requestId: 'heal', expectedRevision: 2, type: 'play-card', instanceId: 'custom-card-1' };
  const healed = await request(app.address, actionPath, 'POST', command);
  assert.equal(healed.status, 200); assert.equal(healed.body.battle.state.breakdown.player, 1);
  assert.ok(healed.body.events.some(e => e.type === 'HealthRestored'));
  await app.close(); app = await createApp(options);
  assert.deepEqual((await request(app.address, `${prefix}/${id}`)).body.battle, healed.body.battle);
  const replay = await request(app.address, actionPath, 'POST', command);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.battle, healed.body.battle);
  config.addEnemySkills['990'] = {effects:[]};
  await writeFile(customScenarioPath, JSON.stringify(config));
  await assert.rejects(loadCustomScenario(base,customScenarioPath), /namespace/);
});
async function customFile(t) {
  const files = await fixture(t);
  const customScenarioPath = join(files.directory, 'custom.json');
  await writeFile(customScenarioPath, bytes);
  return { ...files, customScenarioPath };
}

test('custom enemy schedules preserve ordered repeated skills and reject unknown references', async t => {
  const files = await customFile(t), input = JSON.parse(bytes), before = JSON.stringify(base);
  input.enemyIntents = [['990','992','990']];
  await writeFile(files.customScenarioPath,JSON.stringify(input));
  const scenario = await loadCustomScenario(base,files.customScenarioPath);
  assert.deepEqual(scenario.definition.enemyIntents,[['990','992','990']]);
  assert.equal(JSON.stringify(base),before);
  assert.ok(Object.isFrozen(scenario.definition.enemyIntents[0]));
  for (const schedule of [[['missing']], '990', [null]]) {
    input.enemyIntents = schedule;
    await writeFile(files.customScenarioPath,JSON.stringify(input));
    await assert.rejects(loadCustomScenario(base,files.customScenarioPath));
  }
});

test('custom data adds namespaced cards without changing any original scenario data', async t => {
  const files = await customFile(t), before = JSON.stringify(base);
  const result = await loadCustomScenario(base, files.customScenarioPath);
  assert.equal(JSON.stringify(base), before);
  assert.match(result.title, /^自定义 · /);
  assert.match(result.notice, /不是原版关卡/);
  assert.equal(result.provenance.mode, 'custom-content');
  assert.equal(result.provenance.baseDefinitionId, base.definition.id);
  assert.deepEqual(result.provenance.base, base.provenance);
  for (const [id, card] of Object.entries(base.definition.cards)) assert.deepEqual(result.definition.cards[id], card);
  assert.equal(result.definition.energyPerRound, 3);
  assert.equal(result.definition.cards['custom:guard-draw'].effects[0].amount, '600');
  assert.ok(Object.isFrozen(result.definition.cards['custom:guard-draw'].effects));
  assert.equal((await loadCustomScenario(base, files.customScenarioPath)).definition.id, result.definition.id);
  const changed = JSON.parse(bytes); changed.addCards['custom:guard-draw'].effects[0].amount = '601';
  await writeFile(files.customScenarioPath, JSON.stringify(changed));
  assert.notEqual((await loadCustomScenario(base, files.customScenarioPath)).definition.id, result.definition.id);
});

test('overwrites, unsupported effects, missing cards and unusable hand limits are rejected', async t => {
  const files = await customFile(t);
  const changes = [
    input => { input.addCards['110001'] = input.addCards['custom:guard-draw']; },
    input => { input.addCards['custom:guard-draw'].effects = [{ type: 'script', code: 'throw 1' }]; },
    input => { input.deck[0] = 'custom:missing'; },
    input => { input.rules.handLimit = 11; },
    input => { input.rules.energyPerRound = -1; },
    input => { input.deck = ['110001']; },
    input => { input.player = { id: 'fake' }; },
  ];
  for (const change of changes) {
    const input = JSON.parse(bytes); change(input);
    await writeFile(files.customScenarioPath, JSON.stringify(input));
    await assert.rejects(loadCustomScenario(base, files.customScenarioPath));
  }
});

test('oversized and malformed UTF8 configurations fail before opening a save', async t => {
  const files = await customFile(t);
  for (const invalid of [Buffer.alloc(65537, 32), Buffer.from([0xff, 0xfe]), Buffer.from('{')]) {
    await writeFile(files.customScenarioPath, invalid);
    await assert.rejects(createApp({ ...files, tutorialDirectory, port: 0 }));
    assert.equal(existsSync(files.savePath), false);
    assert.equal(existsSync(files.savePath + '.battles'), false);
  }
});

test('custom mode cannot bypass the verified tutorial source loader', async t => {
  const files = await customFile(t);
  await assert.rejects(createApp({ ...files, port: 0 }), /requires verified tutorial/);
  await assert.rejects(createApp({ ...files, tutorialDirectory: join(files.directory, 'missing'), port: 0 }), /Invalid tutorial evidence/);
  assert.equal(existsSync(files.savePath), false);
});

test('HTTP custom shield/draw persists, retries once, survives config edits and finishes using its saved rules', async t => {
  const files = await customFile(t);
  const options = { ...files, tutorialDirectory, port: 0 };
  let app = await createApp(options);
  files.cleanupWith(() => app.close());
  assert.equal((await request(app.address, '/status')).body.battleMode, 'custom-content');
  assert.match((await request(app.address, '/tutorial')).body.title, /守势试炼/);
  const profile = (await request(app.address, '/profiles', 'POST', { displayName: '自定义验证' })).body.profile;
  const prefix = `/profiles/${profile.id}/battles`;
  let battle = (await request(app.address, prefix, 'POST', { requestId: 'custom-create', seed: 5000 })).body.battle;
  const command = { requestId: 'guard', expectedRevision: battle.revision, type: 'play-card', instanceId: 'custom-card-1' };
  const played = await request(app.address, `${prefix}/${battle.id}/actions`, 'POST', command);
  assert.equal(played.status, 200);
  battle = played.body.battle;
  assert.equal(battle.state.player.shield.decimal, '600');
  assert.equal(battle.state.energy, 2);
  assert.equal(battle.state.piles.hand.length, 3);
  assert.ok(played.body.events.some(e => e.type === 'CardDrawn'));
  const retried = await request(app.address, `${prefix}/${battle.id}/actions`, 'POST', command);
  assert.equal(retried.body.replayed, true);
  assert.deepEqual(retried.body.battle, battle);
  await app.close();
  const changed = JSON.parse(bytes); changed.addCards['custom:guard-draw'].effects[0].amount = '999';
  await writeFile(files.customScenarioPath, JSON.stringify(changed));
  app = await createApp(options);
  assert.notEqual((await request(app.address, '/tutorial')).body.definition.id, battle.scenario.definition.id);
  assert.deepEqual((await request(app.address, `${prefix}/${battle.id}`)).body.battle, battle);
  assert.equal((await request(app.address, `${prefix}/${battle.id}/actions`, 'POST', command)).body.replayed, true);
  let action = 0;
  while (battle.state.status === 'player-turn' && action < 100) {
    const cards = battle.state.piles.hand.map(instanceId => {
      const card = battle.scenario.definition.cards[battle.state.cards.find(c => c.instanceId === instanceId).cardId];
      return { instanceId, card, damage: card.effects.filter(e => e.type === 'damage').reduce((n, e) => n + Number(e.amount), 0) };
    }).filter(item => item.card.cost <= battle.state.energy).sort((a, b) => b.damage - a.damage);
    const response = await request(app.address, `${prefix}/${battle.id}/actions`, 'POST', {
      requestId: `continue-${++action}`, expectedRevision: battle.revision,
      ...(cards.length ? { type: 'play-card', instanceId: cards[0].instanceId } : { type: 'end-turn' }),
    });
    assert.equal(response.status, 200, JSON.stringify(response.body));
    battle = response.body.battle;
  }
  assert.equal(battle.state.status, 'won');
  assert.equal(battle.scenario.definition.cards['custom:guard-draw'].effects[0].amount, '600');
  const fresh = (await request(app.address, prefix, 'POST', { requestId: 'after-edit', seed: 5000 })).body.battle;
  assert.equal(fresh.scenario.definition.cards['custom:guard-draw'].effects[0].amount, '999');
  await app.close();
  app = await createApp({ ...options, customScenarioPath: undefined });
  assert.equal((await request(app.address, '/status')).body.battleMode, 'explicit-reconstruction');
  assert.deepEqual((await request(app.address, `${prefix}/${battle.id}`)).body.battle, battle);
  assert.equal((await request(app.address, '/tutorial')).body.definition.id, base.definition.id);
});
