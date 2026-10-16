import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadMainline, projectMainline, completedChallenge, sourceChallengeGate } from '../src/mainline.js';

const directory = fileURLToPath(new URL('../../analysis/mainline-progression', import.meta.url));
const source = { skip: !existsSync(join(directory,'prologue.json')) && 'Run tools/prepare_prologue_progression.py against the pinned APK' };
const load = () => loadMainline(directory, { resolve: id => id === 'tutorial-5000' ? {} : null });
const state = { profileId: 'profile', revision: 0, completed: [], updatedAt: null };
test('Source prologue keeps the 5000 -> 1703 link, no loot, and unavailable boss separate from unlock', source, async () => {
  const d = await load();
  const before = projectMainline(d,state);
  assert.deepEqual(before.challenges.map(n=>[n.id,n.battleId,n.status,n.executable,n.hasLoot]),
    [[3997,5000,'available',true,false],[3998,1703,'locked',false,false]]);
  const after = projectMainline(d,{...state,revision:1,completed:[{challengeId:3997}]});
  assert.equal(after.challenges[1].status,'available');
  assert.equal(after.challenges[1].executable,false);
  assert.equal(before.activityDatas,null);
  assert.equal(before.challenges[0].recordPresent,false);
  assert.equal(before.challenges[0].successTime,null);
  assert.deepEqual(after.activityDatas,{ '2': { '3997': { successTime: 1 } } });
  assert.equal(after.challenges[1].recordPresent,false);
  assert.equal(after.challenges[1].successTime,null);
  assert.equal(Object.hasOwn(after.activityDatas['2'],'3998'),false);
  assert.deepEqual(before.completed,[]);
});
test('A missing activityDatas key stays locked, while successTime 0 is present but not a success', () => {
  const node = id => ({ id, predecessors: id === 3998 ? [3997] : [] });
  assert.deepEqual(sourceChallengeGate(node(3997), {}), { recordPresent: false, successTime: null, status: 'available' });
  assert.deepEqual(sourceChallengeGate(node(3998), {}), { recordPresent: false, successTime: null, status: 'locked' });
  assert.deepEqual(sourceChallengeGate(node(3997), { '3997': { successTime: 0 } }),
    { recordPresent: true, successTime: 0, status: 'available' });
  assert.deepEqual(sourceChallengeGate(node(3998), { '3997': { successTime: 0 } }),
    { recordPresent: false, successTime: null, status: 'available' });
  assert.equal(sourceChallengeGate(node(3997), { '3997': { successTime: 1 } }).status, 'passed');
});
test('Only a won, source-bound battle can complete a one-time prologue challenge', source, async () => {
  const d=await load();
  const b={id:'battle',scenario:{encounterId:'tutorial-5000'},state:{status:'won'}};
  assert.equal(completedChallenge(d,state,b).id,3997);
  for(const status of ['player-turn','lost']) assert.throws(()=>completedChallenge(d,state,{...b,state:{status}}),{code:'BATTLE_NOT_WON'});
  assert.throws(()=>completedChallenge(d,state,{...b,scenario:{encounterId:'city-preview-10405'}}),{code:'BATTLE_NOT_MAINLINE'});
  assert.throws(()=>completedChallenge(d,{...state,completed:[{challengeId:3997,battleId:'other'}]},b),{code:'CHALLENGE_ALREADY_COMPLETED'});
});
test('Modified source evidence is rejected before a progression definition is loaded', source, async t => {
  const dir=await mkdtemp(join(tmpdir(),'hczs-mainline-source-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  const raw=await readFile(join(directory,'prologue.json'));
  await writeFile(join(dir,'prologue.json'),Buffer.concat([raw,Buffer.from(' ')]));
  await assert.rejects(()=>loadMainline(dir,{resolve:()=>({})}),/source changed/);
});
