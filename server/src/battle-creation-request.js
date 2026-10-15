import { ServiceError, requireObject } from './errors.js';

export function creationRequest(input) {
  requireObject(input, ['requestId', 'seed', 'encounterId'], ['requestId']);
  if (typeof input.requestId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/.test(input.requestId) ||
      ('seed' in input && (!Number.isSafeInteger(input.seed) || input.seed < 0 || input.seed > 0xffffffff)) ||
      ('encounterId' in input && (typeof input.encounterId !== 'string' || !/^[a-z][a-z0-9-]{0,79}$/.test(input.encounterId)))) {
    throw new ServiceError('INVALID_INPUT', 'Invalid battle creation request');
  }
  // Preserve the original serialization when the optional encounter ID is absent,
  // so pre-migration receipts remain retryable without a schema rewrite.
  return JSON.stringify({ requestId: input.requestId, ...('seed' in input ? { seed: input.seed } : {}),
    ...('encounterId' in input ? { encounterId: input.encounterId } : {}) });
}

export function requireSelectedScenario(scenario, input) {
  if (!scenario) throw new ServiceError('ENCOUNTER_UNAVAILABLE', 'Encounter is not enabled on this server', 404);
  if ('encounterId' in input && scenario.encounterId !== input.encounterId) {
    throw new Error('Encounter selection does not match the saved scenario');
  }
}
