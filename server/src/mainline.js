import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ServiceError } from './errors.js';

const SOURCE_SHA = 'd7fdba3c26a4030a6abb26ddd960424bf44db2f8fc6259333a5c2aab9e188b19';
export const MAINLINE_POLICY = 'local-prologue-progress-v1';
export const mainlineContentId = definition => createHash('sha256').update(JSON.stringify({
  sourceSha256: definition.sourceSha256, policy: definition.policy, nodes: definition.nodes })).digest('hex');
/** The first persisted format had no snapshot; retain its exact known binding. */
export function legacyMainlineDefinition(definition) {
  const legacy = { ...definition, nodes: definition.nodes.map(node => ({ ...node,
    encounterId: node.battleId === 5000 ? 'tutorial-5000' : null })) };
  legacy.contentId = mainlineContentId(legacy);
  return legacy;
}
function freeze(value) {
  if (value && typeof value === 'object') { for (const child of Object.values(value)) freeze(child); Object.freeze(value); }
  return value;
}
export async function loadMainline(directory, encounters) {
  const raw = await readFile(join(directory, 'prologue.json'));
  if (createHash('sha256').update(raw).digest('hex') !== SOURCE_SHA) throw Error('Reviewed prologue source changed');
  const source = JSON.parse(raw);
  if (source.activityId !== 2 || source.nodes.length !== 2 || !encounters?.resolve('tutorial-5000')) throw Error('Prologue requires recovered tutorial evidence');
  const nodes = source.nodes.map(node => ({ ...node, encounterId: node.battleId === 5000 ? 'tutorial-5000' : null }));
  const contentId = mainlineContentId({ sourceSha256: SOURCE_SHA, policy: MAINLINE_POLICY, nodes });
  return freeze({ activityId: 2, name: source.name, contentId, sourceSha256: SOURCE_SHA, policy: MAINLINE_POLICY,
    nodes, evidenceKind: source.authority,
    initialStateAuthority: 'local-fresh-profile-policy; not recovered original account state' });
}

/** Source activityDatas gate. A missing key is not successTime 0, and key presence is not the same as success. */
export function sourceChallengeGate(node, records) {
  const own = Object.hasOwn(records, String(node.id)) ? records[String(node.id)] : undefined;
  const recordPresent = own !== undefined;
  const successTime = recordPresent ? own.successTime : null;
  const succeeded = recordPresent && typeof successTime === 'number' && successTime > 0;
  const predecessorsPresent = node.predecessors.every(id => Object.hasOwn(records, String(id)));
  return { recordPresent, successTime, status: succeeded ? 'passed' : predecessorsPresent ? 'available' : 'locked' };
}

/** Account-independent source directory + separate local completion state. */
export function projectMainline(definition, state) {
  const records = {};
  for (const row of state.completed) records[String(row.challengeId)] = { successTime: 1 };
  const activityKey = String(definition.activityId);
  return { profileId: state.profileId, activityId: definition.activityId, contentId: definition.contentId,
    policy: definition.policy, revision: state.revision, updatedAt: state.updatedAt,
    initialStateAuthority: definition.initialStateAuthority,
    activityDatas: Object.keys(records).length ? { [activityKey]: records } : null,
    challenges: definition.nodes.map(node => ({ id: node.id, name: node.name, subtitle: node.subtitle,
      battleId: node.battleId, predecessors: node.predecessors, hasLoot: node.hasLoot,
      ...sourceChallengeGate(node, records), encounterId: node.encounterId,
      executable: node.encounterId !== null,
      ...(node.encounterId === null ? { unavailableReason: 'original-boss-mechanics-and-client-not-restored' } : {}) })),
    completed: state.completed };
}

export function completedChallenge(definition, state, battle) {
  if (battle.state.status !== 'won') throw new ServiceError('BATTLE_NOT_WON', 'Only an authoritative victorious battle can advance progress', 409);
  const node = definition.nodes.find(row => row.encounterId !== null && row.encounterId === battle.scenario.encounterId);
  if (!node) throw new ServiceError('BATTLE_NOT_MAINLINE', 'This battle is not bound to a recovered mainline challenge', 409);
  if (state.completed.some(row => row.battleId === battle.id || row.challengeId === node.id))
    throw new ServiceError('CHALLENGE_ALREADY_COMPLETED', 'This one-time challenge was already settled', 409);
  if (!node.predecessors.every(id => state.completed.some(row => row.challengeId === id)))
    throw new ServiceError('CHALLENGE_LOCKED', 'Required challenges have not been completed', 409);
  if (node.hasLoot !== false || node.maxCompletions !== 1) throw Error('Unsupported mainline reward/completion policy');
  return node;
}
