import { readFile, writeFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

/** Independent wire evidence, not just a count of native retry callbacks. */
export function verifySessionHttp({ manifest, native, events }) {
  const checks = {};
  const profilePath = `/api/rebuild/v1/profiles/${native.profileId}`;
  const battlePath = `${profilePath}/battles/${native.battleId}`;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const requests = events.filter(e => e.phase === 'ue-request');
  checks.isolatedIdentity = manifest.mode === 'isolated-native-session-test' && /^hczs_test_ue_[0-9a-f]{32}$/.test(manifest.mongoDatabase)
    && Number.isInteger(manifest.port) && manifest.port > 0 && manifest.port <= 65535 && manifest.port !== 7460 && native.port === manifest.port
    && uuid.test(native.profileId) && uuid.test(native.battleId);
  checks.nativePassed = native.passed === true && native.mode === 'ue-native-http-session-not-ui-gameplay';
  checks.explicitSelection = native.explicitProfileSelection === true;
  checks.ownCardAndTurn = native.cardPlayed === true && native.turnEnded === true;
  checks.newInstanceRestoration = native.newGameInstanceRestored === true;
  checks.serverTerminal = ['won','lost'].includes(native.outcome) && Number.isSafeInteger(native.finalRevision) && native.finalRevision > 1;
  checks.actualCardAndTurnRequests = requests.some(e => e.path === `${battlePath}/actions` && e.type === 'play-card' && e.status === 200)
    && requests.some(e => e.path === `${battlePath}/actions` && e.type === 'end-turn' && e.status === 200);
  checks.freshInstanceReads = requests.filter(e => e.method === 'GET' && e.path === '/api/rebuild/v1/bootstrap' && e.status === 200).length >= 2
    && requests.some(e => e.method === 'GET' && e.path === profilePath && e.status === 200)
    && requests.filter(e => e.method === 'GET' && e.path === battlePath && e.status === 200 && !e.droppedAfterRead).length >= 3;
  if (native.ultimateGeneratedInActualHand || native.ultimateReceiptConfirmedAfterGet) {
    const ultimates = requests.filter(e => e.method === 'POST' && e.path === `${battlePath}/actions`
      && e.status === 200 && e.type === 'play-card' && e.receiptEvents?.some(v => v.type === 'CardPlayed' && v.cardId === '410104'));
    const damage = e => e.receiptEvents.filter(v => v.type === 'DamageApplied' && v.actor === 'player' && v.target === 'enemy');
    checks.ultimateNativeConfirmed = native.ultimateGeneratedInActualHand === true && native.ultimateReceiptConfirmedAfterGet === true;
    checks.ultimateWireReceipt = ultimates.length > 0 && ultimates.every(e => e.receiptEvents.some(v =>
      v.type === 'CardPlayed' && v.cardId === '410104' && v.instanceId === e.instanceId));
    checks.ultimateDamageOrder = ultimates.length > 0 && ultimates.every(e => {
      const hits = damage(e);
      return hits.length > 0 && hits.length <= 8 && hits.every((v, i) => v.effectIndex === i)
        && (hits.length === 8 || e.receiptEvents.some(v => v.type === 'BattleEnded' && v.status === 'won' && v.reason === 'enemy-defeated'));
    });
    checks.ultimateReadBeforeNextWrite = ultimates.length > 0 && ultimates.every(e => {
      const later = requests.slice(requests.indexOf(e) + 1);
      const nextWrite = later.findIndex(v => v.method !== 'GET');
      return (nextWrite < 0 ? later : later.slice(0, nextWrite)).some(v => v.method === 'GET'
        && v.path === battlePath && v.status === 200 && !v.droppedAfterRead && v.revision === e.revision);
    });
    checks.ultimateNativeDamageMatchesWire = ultimates.length > 0 && damage(ultimates.at(-1)).length === native.ultimateDamageEvents;
  }
  if (manifest.faults) {
    const dropIndex = events.findIndex(e => e.phase === 'ue-request' && e.method === 'POST' && e.path === `${profilePath}/battles` && e.droppedAfterCommit === true);
    const dropped = events[dropIndex];
    const replayIndex = events.findIndex((e, i) => i > dropIndex && e.phase === 'ue-request' && e.path === dropped?.path && e.method === 'POST' && e.status === 201 && e.replayed === true);
    const replay = events[replayIndex];
    checks.sameCreationRequestAndPayload = dropIndex >= 0 && replayIndex > dropIndex && dropped.requestId === replay.requestId
      && /^[0-9a-f]{64}$/.test(dropped.bodySha256) && dropped.bodySha256 === replay.bodySha256;
    checks.historicalCreationReceipt = dropIndex >= 0 && replayIndex > dropIndex && replay.revision === 1 && dropped.advancedRevision > replay.revision;
    const partialIndex = events.findIndex((e, i) => i > replayIndex && e.phase === 'ue-request' && e.path === battlePath && e.method === 'GET' && e.droppedAfterRead === true);
    const partial = events[partialIndex];
    checks.partialReadReallyTransmitted = partialIndex > replayIndex && partial.wireFailure === 'truncated-http-body'
      && Number.isInteger(partial.declaredBytes) && Number.isInteger(partial.deliveredBytes) && partial.deliveredBytes > 0 && partial.deliveredBytes < partial.declaredBytes;
    const retryReadIndex = events.findIndex((e, i) => i > partialIndex && e.phase === 'ue-request' && e.path === battlePath && e.method === 'GET' && e.status === 200 && !e.droppedAfterRead);
    const retryRead = events[retryReadIndex];
    checks.confirmedReadRetriesOnlyGet = retryReadIndex > partialIndex && partialIndex > replayIndex &&
      !events.slice(partialIndex + 1, retryReadIndex).some(e => e.phase === 'ue-request' && e.method !== 'GET');
    checks.historicalReceiptFetchedCurrentState = replayIndex >= 0 && retryReadIndex > replayIndex && retryRead.revision >= dropped.advancedRevision && retryRead.revision > replay.revision;
    checks.nativeWriteAndReadRetryPaths = native.unconfirmedWriteRetries >= 1 && native.confirmedReadRetries >= 1;
    const conflictIndex = events.findIndex(e => e.phase === 'ue-request' && e.path === `${battlePath}/actions` && e.status === 409);
    const conflict = events[conflictIndex];
    const race = events.slice(0, conflictIndex).findLast(e => e.phase === 'injected-cas-race');
    const conflictReadIndex = events.findIndex((e, i) => i > conflictIndex && e.phase === 'ue-request' && e.path === battlePath && e.method === 'GET' && e.status === 200 && !e.droppedAfterRead);
    const conflictRead = events[conflictReadIndex];
    const newIntentIndex = events.findIndex((e, i) => i > conflictReadIndex && e.phase === 'ue-request' && e.path === `${battlePath}/actions` && e.status === 200);
    const newIntent = events[newIntentIndex];
    checks.casRaceActuallyReachedClient = conflictIndex >= 0 && race?.before === conflict.expectedRevision && race.after > race.before && native.conflictReloaded === true;
    checks.conflictReadBeforeNewIntent = conflictIndex >= 0 && conflictReadIndex > conflictIndex && newIntentIndex > conflictReadIndex
      && conflictRead.revision >= race?.after && newIntent.expectedRevision === conflictRead.revision && newIntent.requestId !== conflict.requestId
      && !events.slice(conflictIndex + 1, conflictReadIndex).some(e => e.phase === 'ue-request' && e.method !== 'GET');
  }
  const failed = Object.entries(checks).filter(([,value]) => !value).map(([name]) => name);
  return { passed: failed.length === 0, mode: 'native-http-plus-independent-wire-evidence', faultMode: Boolean(manifest.faults), checks, failed };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: {'record-directory': { type: 'string' }} });
  if (!values['record-directory']) throw Error('Pass --record-directory <isolated test run>');
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const allowed = resolve(root, 'analysis/unreal/session-test'), directory = resolve(values['record-directory']);
  const rel = relative(allowed, directory); if (!rel || rel.startsWith('..') || rel.includes(':')) throw Error('Record directory must be a child of analysis/unreal/session-test');
  const [manifestText, nativeText, traceText] = await Promise.all(['server.json','http-result.json','http-trace.jsonl'].map(name => readFile(resolve(directory, name), 'utf8')));
  const result = verifySessionHttp({ manifest: JSON.parse(manifestText), native: JSON.parse(nativeText), events: traceText.trim().split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line)) });
  await writeFile(resolve(directory, 'wire-verification.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2)); if (!result.passed) process.exitCode = 1;
}
