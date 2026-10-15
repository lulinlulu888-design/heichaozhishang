import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { int, float, fromTagged, toTagged, multiply, classicDivide, calcDamage } from '../../packages/battle-core/src/index.js';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const SOURCE_SHA = '986d405c0ced3b796b4655e68b7887d4e7ce6e71e7a4dbc5fa7ad17cb8cdafe5';
const scalarTree = value => typeof value === 'number' ? int(value) :
  value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, scalarTree(item)])) : value;
const requireSource = (condition, message) => { if (!condition) throw new Error('Invalid city ultimate evidence: ' + message); };

// Pin recovered APK identities and literal/instruction evidence, never the report's
// currentImplementation hashes, prose, local extraction paths or JSON formatting.
const SOURCE_KEYS = ['apk_member', 'index', 'filename', 'name_hash', 'offset', 'stored_size',
  'original_size', 'payload_sha256', 'decoded_sha256'];
const identity = source => Object.fromEntries(SOURCE_KEYS.filter(key => Object.hasOwn(source, key)).map(key => [key, source[key]]));
const canonical = value => Array.isArray(value) ? '[' + value.map(canonical).join(',') + ']' :
  value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}' : JSON.stringify(value);
export function ultimateSourceDigest(evidence) {
  const group = (name, fields) => Object.fromEntries(Object.entries(evidence[name]).map(([key, entry]) =>
    [key, { source: identity(entry.source), ...Object.fromEntries(fields.filter(field => Object.hasOwn(entry, field)).map(field => [field, entry[field]])) }]));
  return sha(canonical({ schemaVersion: evidence.schemaVersion,
    tables: group('tables', ['rows']),
    code: group('code', ['code_objects', 'constant_path', 'instructions']),
    graphs: group('graphs', ['constant_index', 'load_offset', 'raw_json_sha256', 'graph']),
    reverseIndexes: group('reverseIndexes', ['constructor_offset', 'assignment_offset', 'total_keys', 'requested']),
  }));
}
export function validateUltimateEvidence(evidence) {
  const digest = ultimateSourceDigest(evidence);
  requireSource(digest === SOURCE_SHA, 'canonical APK source SHA-256 mismatch');
  return digest;
}

/** Only called while constructing a new city definition. Embedded saved definitions are never upgraded. */
export async function addCityUltimate(definition, base, encounter) {
  const raw = await readFile(new URL('../../analysis/battle-rules/ultimate-trigger.json', import.meta.url));
  const evidence = JSON.parse(raw), tables = evidence.tables;
  const sourceSha256 = validateUltimateEvidence(evidence);
  requireSource(encounter === 10405 && tables.current_city_encounter.rows.some(row => row.id === encounter), 'unknown encounter');
  requireSource(!tables.courses.rows.some(row => row.fields.FirstBattleID === encounter), 'tutorial gate must be handled explicitly');
  const card = tables.elsa_card.rows.find(row => row.id === 410104)?.fields;
  const skill = tables.elsa_skill.rows.find(row => row.id === 410104)?.fields;
  const link = tables.elsa_special_link_and_legacy_fields.rows.find(row => row.id === 1)?.fields;
  requireSource(card?.CARD_TYPE === 7 && card.COST === 0 && card.CARD_DISAPPEAR === true && card.CHARTYPE === 1 &&
    card.SKILL_ID === 410104 && skill?.SKILL_TARGET_TYPE === 1 && link?.SpecialSkillCardID === 410104, 'unsupported special card');

  const normalRaw = await readFile(new URL('../../analysis/first-encounter/player-cards.json', import.meta.url));
  requireSource(sha(normalRaw) === base.policies.sourcePins['player-cards.json'].sha256, 'normal card SHA-256 mismatch');
  const normal = JSON.parse(normalRaw);
  for (const [cardId, entry] of Object.entries(definition.cards)) {
    const source = normal.rows.find(row => String(row.id) === cardId)?.fields;
    const owners = base.provenance.deckOwnership.filter(row => row.cardId === cardId);
    requireSource(source?.CHARTYPE === 1 && source.CARD_TYPE === 0 && source.CARD_DISAPPEAR === false &&
      (source.SPECIALSKILL_POINT ?? 1) === 1 && owners.length > 0 && owners.every(row => row.ownerCharacterId === '1'), 'unsupported card ownership or points');
    Object.assign(entry, { ownerId: '1', cardType: source.CARD_TYPE, specialPoints: 1, removeOnLeaveHand: false });
  }
  const attack = fromTagged(base.provenance.baseline.baseStatsTagged.PropAtk);
  const states = tables.states.rows.filter(row => row.fields.OwnerSkill === 410104).sort((a, b) => a.fields.OwnerIndex - b.fields.OwnerIndex);
  const percentages = [15, 15, 30, 30, 30, 60, 60, 60], calculations = [], effects = [];
  requireSource(states.length === 9, 'expected eight damage states plus energyadd');
  for (let index = 0; index < states.length; index++) {
    const { id, fields: state } = states[index];
    requireSource(id === 371 + index && state.OwnerIndex === index, 'state sequence');
    if (index === 8) {
      // Graph 9093 adds num + num1; the pinned graph's absent num1 default is 0.
      requireSource(state.STORYLINE_NAME === 'energyadd' && state.STORYLINE_PARAM.num === 0 &&
        !Object.hasOwn(state.STORYLINE_PARAM, 'num1'), 'unsupported energy change');
      calculations.push({ stateId: id, operation: 'energyadd', amount: 0, disposition: 'no-op' });
      continue;
    }
    requireSource(state.STORYLINE_NAME === 'SkillState_CauseDamage' && state.RPG_FORMULA === 'PropAtk' &&
      state.RPG_DEFAULT_FORMULA === String(percentages[index]) && state.DAMAGE_TYPE === 1 &&
      state.SKILL_STATE_TARGET_TYPE === 16 && state.STORYLINE_PARAM['#EXTRA_DAMAGE'] === 0, 'unsupported damage state');
    const basic = classicDivide(multiply(attack, int(percentages[index])), float(100));
    const result = calcDamage({ ...scalarTree(base.policies.neutralDamage), rpgAttackType: int(state.DAMAGE_TYPE),
      rpgBasicActionValue: basic, extraDamage: int(0), dstIsPlayer: false });
    effects.push({ type: 'damage', target: 'opponent', amount: result.damage.value.toString() });
    calculations.push({ stateId: id, percentage: percentages[index], base: toTagged(basic), result: toTagged(result.damage) });
  }
  definition.cards['410104'] = { name: card.NAME, cost: card.COST, effects, ownerId: '1', cardType: 7,
    specialPoints: 0, removeOnLeaveHand: true };
  definition.ultimateRules = { policy: 'elsa-combo-reconstruction-v1', ownerId: '1', cardId: '410104', pointsRequired: 3, maxPerRound: 3 };
  return { evidencePath: 'analysis/battle-rules/ultimate-trigger.json', sourceDigestFormat: 'hczs-ultimate-apk-source-v1', sourceSha256,
    loaderSha256: sha(await readFile(new URL('./city-ultimate.js', import.meta.url))), sourceEncounter: encounter,
    sourceTutorialGate: 'not-a-course-entry-default-enabled', originalServerRecovered: false,
    calculations, localDecisions: {
      scope: 'single-owner-preview-only', generationOrder: 'after-effects-and-card-movement', lethalGeneration: 'none',
      fullHand: 'consume-trigger-without-generation-or-queue', zeroPointCard: 'preserve-chain',
      roundReset: 'clear-chain-and-round-generation-count', lethalHits: 'stop-after-lethal-as-existing-session-policy',
      damageProvider: 'source-state-percentages-with-existing-explicit-neutral-policy',
    } };
}
