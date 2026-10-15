import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {loadHeroes} from '../src/heroes.js';
import {heroFixture} from './helpers/hero-fixture.js';

async function directory(t) {
  const dir = await mkdtemp(join(tmpdir(), 'hczs-heroes-'));
  t.after(() => rm(dir, {recursive: true, force: true}));
  return dir;
}
const save = (dir, value) => writeFile(join(dir, 'heroes.json'), JSON.stringify(value));

test('complete directory exposes reviewed Elsa UE hall and Shiranui migration previews only', async t => {
  const dir = await directory(t);
  await save(dir, heroFixture());
  const result = await loadHeroes(dir);
  assert.equal(result.heroes.length, 35);
  assert.equal(result.sources.npkIndex, 8995);
  assert.equal(result.heroes.find(hero => hero.id === 33).name, '不知火');
  assert.equal(result.heroes.some(hero => hero.id === 20), false);
  assert.deepEqual(result.heroes.filter(hero => hero.availability.hallPreview === 'verified').map(hero => hero.id), [1, 33]);
  const elsa = result.heroes.find(hero => hero.id === 1);
  assert.equal(elsa.name, '艾尔莎');
  assert.equal(elsa.hallPreviewVerification.renderer, 'unreal-editor');
  assert.equal(elsa.hallPreviewVerification.platform, 'windows');
  assert.equal(elsa.hallPreviewVerification.sourceAnimation, 'home_stand_idle_1');
  assert.equal(result.heroes.find(hero => hero.id === 33).hallPreviewVerification.renderer, 'legacy-web-preview');
  assert.ok(result.heroes.every(hero => hero.availability.fullBattle === 'not-verified'));
  assert.ok(result.heroes.every(hero => !('owned' in hero) && !('combatEligible' in hero)));
  assert.equal(result.scope, 'recovered-hero-directory');
});

test('optional absence is null, but required absence and present corruption reject', async t => {
  const dir = await directory(t);
  assert.equal(await loadHeroes(dir, {optional: true}), null);
  await assert.rejects(loadHeroes(dir), {code: 'ENOENT'});
  await writeFile(join(dir, 'heroes.json'), '{bad');
  await assert.rejects(loadHeroes(dir, {optional: true}), SyntaxError);
});

test('source identity, completeness, duplicates and name tampering are rejected', async t => {
  const dir = await directory(t);
  for (const modify of [
    fixture => fixture.source.index = 1,
    fixture => fixture.apkSha256 = '0'.repeat(64),
    fixture => fixture.heroes.pop(),
    fixture => fixture.heroes[1].id = 1,
    fixture => fixture.heroes[0].name = '伪造名称',
    fixture => fixture.selection.equals = 0,
  ]) {
    const fixture = heroFixture(); modify(fixture);
    await save(dir, fixture);
    await assert.rejects(loadHeroes(dir, {optional: true}), /Invalid hero directory/);
  }
});

test('untrusted ownership/availability fields cannot grant recovery capability', async t => {
  const dir = await directory(t);
  const fixture = heroFixture();
  fixture.heroes[1].owned = true;
  fixture.heroes[1].availability = {hallPreview: 'verified', fullBattle: 'verified'};
  fixture.recoveryPolicy = 'every-hero-is-playable';
  fixture.reconstructionEvidence = [{heroId: 2, renderer: 'unreal-editor', packagedPlatformsVerified: true}];
  await save(dir, fixture);
  const result = await loadHeroes(dir);
  assert.deepEqual(result.heroes[1].availability, {hallPreview: 'not-integrated', fullBattle: 'not-verified'});
  assert.equal('owned' in result.heroes[1], false);
  assert.equal('hallPreviewVerification' in result.heroes[1], false);
  assert.equal(result.recoveryPolicy, 'hczs-hall-preview-policy-v2');
});

test('oversized input is rejected before JSON parsing', async t => {
  const dir = await directory(t);
  await writeFile(join(dir, 'heroes.json'), ' '.repeat(64 * 1024 + 1));
  await assert.rejects(loadHeroes(dir, {optional: true}), /byte budget exceeded/);
});
