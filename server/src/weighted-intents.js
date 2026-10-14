import { createHash } from 'node:crypto';
import { validateDefinition } from '../../packages/battle-session/src/index.js';

// Local reconstruction PRNG, NOT the missing original server's random algorithm.
// Separate stream from deck shuffling; fixed rounds consume no random draw.
export function weightedIntents(policy, seed, rounds) {
  if (policy?.algorithm !== 'sha256-weighted-intents-v1' || !Number.isInteger(seed) || seed < 0 || seed > 0xffffffff ||
      !Number.isInteger(rounds) || rounds < 1 || rounds > 1000 ||
      !Number.isInteger(policy.divisor) || policy.divisor < 1 ||
      !Number.isInteger(policy.remainder) || policy.remainder < 0 || policy.remainder >= policy.divisor ||
      typeof policy.fixedSkill !== 'string' || !Array.isArray(policy.pool) || !policy.pool.length || policy.pool.length > 100) {
    throw new Error('Invalid weighted enemy selection policy');
  }
  const ids = new Set(); let total = 0;
  for (const row of policy.pool) {
    if (typeof row.skillId !== 'string' || ids.has(row.skillId) || !Number.isSafeInteger(row.weight) || row.weight <= 0) {
      throw new Error('Invalid weighted enemy pool');
    }
    ids.add(row.skillId); total += row.weight;
  }
  if (total > 0x100000000) throw new Error('Weighted enemy pool exceeds uint32');
  const limit = Math.floor(0x100000000 / total) * total;
  return Array.from({ length: rounds }, (_, index) => {
    const round = index + 1;
    if (round % policy.divisor === policy.remainder) return [policy.fixedSkill];
    let value, attempt = 0;
    do {
      value = createHash('sha256').update(`hczs-enemy-intent-v1:${seed}:${round}:${attempt++}`).digest().readUInt32BE(0);
    } while (value >= limit);
    let ticket = value % total;
    for (const row of policy.pool) {
      if (ticket < row.weight) return [row.skillId];
      ticket -= row.weight;
    }
    throw new Error('Unreachable weighted selection');
  });
}

export function materializeEnemySelection(scenario, seed) {
  const policy = scenario.policies?.enemySelection;
  if (!policy) return scenario;
  const result = structuredClone(scenario);
  result.definition.enemyIntents = weightedIntents(policy, seed, result.definition.maxRounds);
  result.provenance = { ...result.provenance, enemySelection: {
    algorithm: policy.algorithm, seed, templateDefinitionId: scenario.definition.id,
    scheduleScope: 'Precomputed local choices persisted with this battle; original PRNG unknown',
  } };
  const digest = createHash('sha256').update(JSON.stringify({ template: scenario.definition.id, policy, seed,
    intents: result.definition.enemyIntents })).digest('hex');
  result.definition.id = scenario.definition.id.slice(0, 20) + '-seed-' + digest;
  validateDefinition(result.definition);
  return result;
}
