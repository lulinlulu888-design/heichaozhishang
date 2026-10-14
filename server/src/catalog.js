import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid recovered catalog: ${message}`);
}

function text(value, field) {
  assert(typeof value === 'string', `${field} must be text`);
  return value;
}

function integer(value, field) {
  assert(Number.isSafeInteger(value) && value >= 0, `${field} must be a nonnegative safe integer`);
  return value;
}

function table(value, expectedIndex) {
  assert(value?.format === 'hczs-static-cdata-v1', 'unsupported extraction format');
  assert(value.source?.apk_member === 'assets/script.npk' && value.source.index === expectedIndex,
    'unexpected source module');
  assert(/^[0-9a-f]{64}$/.test(value.source.decoded_sha256), 'missing source digest');
  assert(Array.isArray(value.rows) && value.rows.length > 0, 'empty table');
  const ids = new Set();
  for (const row of value.rows) {
    integer(row.id, 'id');
    assert(!ids.has(row.id) && row.fields && typeof row.fields === 'object', 'duplicate/malformed row');
    ids.add(row.id);
  }
  return value;
}

/** Explicit projection of recovered literals. No damage or starter-deck inference. */
export async function loadCatalog(directory) {
  const files = ['characters.json', 'cards.json'];
  const raw = await Promise.all(files.map(async file => {
    const path = join(directory, file);
    assert((await stat(path)).size <= 16 * 1024 * 1024, 'table exceeds byte budget');
    return readFile(path);
  }));
  const characters = table(JSON.parse(raw[0]), 8995);
  const cards = table(JSON.parse(raw[1]), 3391);
  const contentId = createHash('sha256').update(raw[0]).update('\0').update(raw[1]).digest('hex');
  const source = value => ({ module: value.source.filename, npkIndex: value.source.index,
    decodedSha256: value.source.decoded_sha256, sourceRowCount: value.total_source_rows });
  const result = {
    schemaVersion: 1,
    contentId,
    scope: 'recovered-literal-sample',
    semantics: 'Display data from APK literals; not an owned roster, starter deck, or evaluated battle rules.',
    characters: characters.rows.map(row => ({
      id: row.id, name: text(row.fields.NAME, 'NAME'),
      englishName: text(row.fields.ENGLISH_NAME, 'ENGLISH_NAME'),
      portraitPath: text(row.fields.CharImage, 'CharImage'),
    })),
    cards: cards.rows.map(row => ({
      id: row.id, name: text(row.fields.NAME, 'NAME'), cost: integer(row.fields.COST, 'COST'),
      level: integer(row.fields.LEVEL, 'LEVEL'), story: text(row.fields.STORY_DESC, 'STORY_DESC'),
      characterImagePath: text(row.fields.CHARACTER_IMAGE, 'CHARACTER_IMAGE'),
      skillId: integer(row.fields.SKILL_ID, 'SKILL_ID'),
    })),
    sources: { characters: source(characters), cards: source(cards) },
  };
  return result;
}
