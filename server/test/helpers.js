import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export async function fixture(t) {
  const directory = await mkdtemp(join(tmpdir(), 'hczs-server-test-'));
  const cleanups = [];
  t.after(async () => {
    for (const close of cleanups.reverse()) await close();
    await rm(directory, { recursive: true, force: true });
  });
  const dataDirectory = join(directory, 'data');
  await mkdir(dataDirectory);
  // Synthetic transport fixtures; real recovered-table checks are separate.
  const make = (index, rows) => ({ format: 'hczs-static-cdata-v1', source: {
    apk_member: 'assets/script.npk', index, filename: 'fixture.py', decoded_sha256: 'a'.repeat(64),
  }, total_source_rows: rows.length, rows });
  await writeFile(join(dataDirectory, 'characters.json'), JSON.stringify(make(8995, [
    { id: 1, fields: { NAME: 'Fixture Hero', ENGLISH_NAME: 'HERO', CharImage: 'fixture.png' } },
    { id: 2, fields: { NAME: 'Fixture Friend', ENGLISH_NAME: 'FRIEND', CharImage: 'friend.png' } },
  ])));
  await writeFile(join(dataDirectory, 'cards.json'), JSON.stringify(make(3391, [
    { id: 410101, fields: { NAME: 'Fixture Card', COST: 1, LEVEL: 1, STORY_DESC: 'Fixture story.',
      CHARACTER_IMAGE: 'fixture-card.png', SKILL_ID: 410101 } },
  ])));
  return { storage: 'sqlite', directory, dataDirectory, savePath: join(directory, 'save.sqlite'),
    cleanupWith: close => cleanups.push(close) };
}

export async function request(address, path, method = 'GET', body, headers = {}) {
  const response = await fetch(address + '/api/rebuild/v1' + path, {
    method, headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: response.status, headers: response.headers, body: response.status === 204 ? null : await response.json() };
}
