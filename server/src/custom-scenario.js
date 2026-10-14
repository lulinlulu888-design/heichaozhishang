// Data-only extension of a verified tutorial. Never evaluates supplied code.
import { open, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { validateDefinition } from '../../packages/battle-session/src/index.js';

const MAX_BYTES = 64 * 1024;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const fail = message => { throw new Error(`Invalid custom scenario: ${message}`); };
function record(value, fields, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== fields.length || Object.keys(value).some(k => !fields.includes(k))) fail(`${name}: missing/unknown fields`);
}
function readable(value, maximum, name) {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum || /[\x00-\x1f\x7f]/.test(value)) fail(`${name}: invalid text`);
}
function freeze(value) {
  if (value && typeof value === 'object') { for (const child of Object.values(value)) freeze(child); Object.freeze(value); }
  return value;
}

export async function loadCustomScenario(base, filename) {
  // Reading a bounded buffer also enforces the limit if a file grows mid-read.
  const handle = await open(filename, 'r');
  let raw;
  try {
    const buffer = Buffer.alloc(MAX_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await handle.read(buffer, length, buffer.length - length, null);
      if (!bytesRead) break;
      length += bytesRead;
    }
    if (length > MAX_BYTES) fail('file exceeds 64 KiB');
    raw = buffer.subarray(0, length);
  } finally { await handle.close(); }
  const input = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
  const statusMode = input?.format === 'hczs-custom-tutorial-v2';
  record(input, ['format', 'id', 'title', 'description', 'addCards', 'deck', 'rules',
    ...(statusMode ? ['statusRules', 'addEnemySkills', 'enemyFallback'] : []),
    ...(Object.hasOwn(input, 'enemyIntents') ? ['enemyIntents'] : [])], 'root');
  if ((!statusMode && input.format !== 'hczs-custom-tutorial-v1') || typeof input.id !== 'string' || !/^[a-z][a-z0-9-]{0,39}$/.test(input.id)) fail('format/id');
  readable(input.title, 40, 'title'); readable(input.description, 160, 'description');
  if (!input.addCards || typeof input.addCards !== 'object' || Array.isArray(input.addCards) ||
      Object.keys(input.addCards).length < 1 || Object.keys(input.addCards).length > 32) fail('addCards count');
  record(input.rules, ['initialDraw', 'roundDraw', 'energyPerRound', 'handLimit', 'maxRounds'], 'rules');
  if (!Number.isInteger(input.rules.handLimit) || input.rules.handLimit < 1 || input.rules.handLimit > 10) fail('handLimit must fit the current 10-slot client');
  if (!Array.isArray(input.deck) || input.deck.length < 1 || input.deck.length > 64) fail('deck count');
  const definition = JSON.parse(JSON.stringify(base.definition));
  if (statusMode) {
    if (!input.addEnemySkills || typeof input.addEnemySkills !== 'object' || Array.isArray(input.addEnemySkills) ||
        Object.keys(input.addEnemySkills).length > 32) fail('addEnemySkills count');
    for (const [id, skill] of Object.entries(input.addEnemySkills)) {
      if (!/^custom:[a-z][a-z0-9-]{0,47}$/.test(id) || Object.hasOwn(definition.enemySkills, id)) fail('custom enemy namespace/collision');
      definition.enemySkills[id] = skill;
    }
    definition.statusRules = input.statusRules;
    definition.enemyFallback = input.enemyFallback;
  }
  for (const [id, card] of Object.entries(input.addCards)) {
    if (!/^custom:[a-z][a-z0-9-]{0,47}$/.test(id) || Object.hasOwn(definition.cards, id)) fail('custom card namespace/collision');
    definition.cards[id] = card;
  }
  definition.deck = input.deck.map((cardId, index) => ({ instanceId: `custom-card-${index + 1}`, cardId }));
  if (!input.deck.some(id => Object.hasOwn(input.addCards, id))) fail('deck must use a new card');
  Object.assign(definition, input.rules);
  // Data-only schedules reference the verified skill inventory. validateDefinition
  // checks shape, bounded counts and references before the configuration is saved.
  if (Object.hasOwn(input, 'enemyIntents')) definition.enemyIntents = input.enemyIntents;
  const configurationSha256 = sha(raw);
  const loaderSha256 = sha(await readFile(new URL('./custom-scenario.js', import.meta.url)));
  const contentHash = sha(JSON.stringify({ baseId: base.definition.id, configurationSha256, loaderSha256, definition }));
  definition.id = `custom-${input.id}-${contentHash}`;
  const checked = validateDefinition(definition);
  return freeze({ definition: checked, title: `自定义 · ${input.title}`,
    notice: `自定义玩法，不是原版关卡。${input.description}`,
    policies: { mode: 'custom-content', base: base.policies, configuration: input },
    provenance: { mode: 'custom-content', originalScenarioRecovered: false,
      baseDefinitionId: base.definition.id, base: base.provenance,
      configurationSha256, loaderSha256, contentHash,
      boundary: 'Custom fixed card effects and rule overrides; original evidence and saved scenarios remain separate.' } });
}
