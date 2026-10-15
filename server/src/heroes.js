import {createHash} from 'node:crypto';
import {open} from 'node:fs/promises';
import {join} from 'node:path';

const APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4';
const DECODED = '1998f8eb7ff9598936b27e61197f96b364a305c01f0f1ca6d1481aba716b6ffb';
const PAYLOAD = '04f68a25876383d410811c454260c3d8f058c08fa573e144fe1c16263d5f8dfb';
const PROJECTION = 'c7dd949b6398079ca1c5fefc1417a66ee00bb2491d3b44509420b79d928fdcba';
// Reviewed reconstruction policy; input JSON can never grant availability.
// Elsa's Windows Editor import, original hall idle and aligned pose were read back.
// Shiranui remains selectable as a previously verified migration reference.
const HALL_PREVIEWS = new Map([
  [1, {renderer: 'unreal-editor', platform: 'windows', sourceAnimation: 'home_stand_idle_1',
    evidence: 'elsa-hall-unreal', verification: 'import-readback-and-aligned-editor-pose',
    sourceModelSha256: '823397c87ae22bbdaa1fc20b07352da0b2b3a252d0f755fb1998dd5d2578b193'}],
  [33, {renderer: 'legacy-web-preview', platform: 'web', evidence: 'shiranui-migration-reference',
    verification: 'recovered-reference-preview'}],
]);
const RECOVERY_POLICY = 'hczs-hall-preview-policy-v2';
const MAX_BYTES = 64 * 1024;
const requireValid = (valid, reason) => { if (!valid) throw new Error(`Invalid hero directory: ${reason}`); };

/** A complete display directory, never an ownership grant or combat eligibility list.
 * Optional mode only tolerates ENOENT. Corrupt/present files fail closed.
 */
export async function loadHeroes(directory, {optional = false} = {}) {
  let handle;
  try { handle = await open(join(directory, 'heroes.json'), 'r'); }
  catch (error) { if (optional && error.code === 'ENOENT') return null; throw error; }
  let raw;
  try {
    requireValid((await handle.stat()).size <= MAX_BYTES, 'byte budget exceeded');
    const buffer = Buffer.alloc(MAX_BYTES + 1);
    let count = 0;
    while (count < buffer.length) {
      const {bytesRead} = await handle.read(buffer, count, buffer.length - count, count);
      if (!bytesRead) break;
      count += bytesRead;
    }
    requireValid(count <= MAX_BYTES, 'byte budget exceeded');
    raw = buffer.subarray(0, count);
  } finally { await handle.close(); }
  const data = JSON.parse(raw.toString('utf8'));
  requireValid(data.schema === 'hczs-server-heroes-v1' && data.apkSha256 === APK, 'schema/APK identity');
  requireValid(data.source?.index === 8995 && data.source.apk_member === 'assets/script.npk'
    && data.source.filename === 'common\\cdata\\character_basic_info.py'
    && data.source.decoded_sha256 === DECODED && data.source.payload_sha256 === PAYLOAD, 'module identity');
  requireValid(data.selection?.field === 'UseRole' && data.selection.equals === 1
    && data.selection.totalSourceRows === 228 && data.selection.selectedRows === 35, 'selection scope');
  requireValid(Array.isArray(data.heroes) && data.heroes.length === 35, 'complete 35-entry directory required');
  const ids = new Set();
  const heroes = data.heroes.map(row => {
    requireValid(Number.isSafeInteger(row?.id) && row.id > 0 && !ids.has(row.id), 'duplicate or invalid ID');
    requireValid(typeof row.name === 'string' && row.name.trim().length > 0 && row.name.length <= 80, 'invalid name');
    ids.add(row.id);
    return {id: row.id, name: row.name};
  }).sort((a, b) => a.id - b.id);
  const digest = createHash('sha256').update(JSON.stringify(heroes)).digest('hex');
  requireValid(data.projectionSha256 === PROJECTION && digest === PROJECTION, 'reviewed names/IDs changed');
  return {
    schemaVersion: 1,
    // The ID also tracks reviewed capability policy changes, even for older input files.
    contentId: createHash('sha256').update(raw).update('\0').update(RECOVERY_POLICY).digest('hex'),
    scope: 'recovered-hero-directory',
    semantics: 'Display directory only; not owned heroes or combat eligibility. Hall availability describes a verified reconstruction preview in the stated renderer/platform; it does not establish complete original visuals, packaged clients or other platforms.',
    recoveryPolicy: RECOVERY_POLICY,
    sources: {apkSha256: APK, module: data.source.filename, npkIndex: 8995, decodedSha256: DECODED,
      payloadSha256: PAYLOAD, projectionSha256: PROJECTION, sourceRowCount: 228, selectedRowCount: 35, filter: 'UseRole=1'},
    heroes: heroes.map(hero => ({...hero, availability: {
      hallPreview: HALL_PREVIEWS.has(hero.id) ? 'verified' : 'not-integrated',
      fullBattle: 'not-verified',
    }, ...(HALL_PREVIEWS.has(hero.id) ? {hallPreviewVerification: {...HALL_PREVIEWS.get(hero.id)}} : {})})),
  };
}
