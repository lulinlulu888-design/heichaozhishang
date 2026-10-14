import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';
import { fixture, request } from './helpers.js';

async function start(files, tutorialDirectory) {
  const process = spawn(globalThis.process.execPath, [fileURLToPath(new URL('../src/index.js', import.meta.url)),
    '--port', '0', '--data-directory', files.dataDirectory, '--save-path', files.savePath,
    ...(tutorialDirectory ? ['--tutorial-directory', tutorialDirectory] : ['--no-tutorial'])],
  { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const ended = once(process, 'exit');
  let errorText = '';
  process.stderr.on('data', chunk => { errorText += chunk; });
  const lines = createInterface({ input: process.stdout });
  const address = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { process.kill(); reject(new Error('Server startup timed out')); }, 10_000);
    lines.on('line', line => {
      const value = JSON.parse(line);
      if (value.event === 'ready') { clearTimeout(timeout); resolve(value.address); }
    });
    process.once('error', error => { clearTimeout(timeout); reject(error); });
    process.once('exit', code => { clearTimeout(timeout); reject(new Error(`Server exit ${code}: ${errorText}`)); });
  });
  return { address, async stop() {
    process.kill();
    await ended;
    lines.close();
  } };
}

test('a new Node process recovers a committed selection after the previous process exits', async t => {
  const files = await fixture(t);
  let running = await start(files);
  files.cleanupWith(async () => { if (running) await running.stop(); });
  const { body: { profile } } = await request(running.address, '/profiles', 'POST', { displayName: '重启恢复' });
  const { body: { profile: saved } } = await request(running.address, `/profiles/${profile.id}`, 'PATCH',
    { expectedRevision: 1, selectedCharacterId: 2 });
  await running.stop();
  running = null;
  running = await start(files);
  const restored = await request(running.address, `/profiles/${profile.id}`);
  assert.deepEqual(restored.body.profile, saved);
  assert.equal(restored.body.profile.selectedCharacterId, 2);
});

test('a new Node process resumes a committed tutorial battle and its command receipt', async t => {
  const files = await fixture(t);
  const tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url));
  let running = await start(files, tutorialDirectory);
  files.cleanupWith(async () => { if (running) await running.stop(); });
  const { body: { profile } } = await request(running.address, '/profiles', 'POST', { displayName: '战斗进程恢复' });
  const base = `/profiles/${profile.id}/battles`;
  const created = await request(running.address, base, 'POST', { requestId: 'create-before-exit', seed: 7788 });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const battle = created.body.battle;
  const command = { requestId: 'card-before-exit', expectedRevision: 1, type: 'play-card', instanceId: battle.state.piles.hand[0] };
  const saved = await request(running.address, `${base}/${battle.id}/actions`, 'POST', command);
  assert.equal(saved.status, 200, JSON.stringify(saved.body));
  await running.stop(); running = null;
  running = await start(files, tutorialDirectory);
  assert.deepEqual((await request(running.address, `${base}/${battle.id}`)).body.battle, saved.body.battle);
  const replay = await request(running.address, `${base}/${battle.id}/actions`, 'POST', command);
  assert.equal(replay.status, 200);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.battle, saved.body.battle);
  const next = await request(running.address, `${base}/${battle.id}/actions`, 'POST',
    { requestId: 'turn-after-restart', expectedRevision: 2, type: 'end-turn' });
  assert.equal(next.status, 200, JSON.stringify(next.body));
  assert.equal(next.body.battle.state.round, 2);
});
