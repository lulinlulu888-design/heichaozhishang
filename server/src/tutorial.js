import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import {
  int, float, fromTagged, toTagged, add, multiply, classicDivide, compare, calcDamage, calcBlock,
} from '../../packages/battle-core/src/index.js';
import { validateDefinition } from '../../packages/battle-session/src/index.js';

const DEFAULT_DIRECTORY = fileURLToPath(new URL('../../analysis/first-encounter/', import.meta.url));
const POLICY_URL = new URL('../data/tutorial-policy.json', import.meta.url);
const sha = value => createHash('sha256').update(value).digest('hex');
const requireEvidence = (condition, message) => {
  if (!condition) throw new Error(`Invalid tutorial evidence: ${message}`);
};
const same = (actual, expected, label) => requireEvidence(isDeepStrictEqual(actual, expected), label);
const nonnegative = value => Number.isSafeInteger(value) && value >= 0;

function validateTable(table, expected, label) {
  for (const [key, value] of Object.entries(expected.source)) same(table?.source?.[key], value, `${label}.source.${key}`);
  requireEvidence(Array.isArray(table.rows), `${label}.rows missing`);
  const rows = new Map();
  for (const row of table.rows) {
    requireEvidence(nonnegative(row.id) && !rows.has(row.id), `${label}: duplicate or invalid row`);
    rows.set(row.id, row);
  }
  same([...rows.keys()].sort((a, b) => a - b), Object.keys(expected.rows).map(Number).sort((a, b) => a - b), `${label}: unexpected rows`);
  const projection = { source: table.source, rows: [] };
  for (const [id, fields] of Object.entries(expected.rows)) {
    const row = rows.get(Number(id));
    const position = row.source;
    requireEvidence(nonnegative(position?.bytecode_start) &&
      position.bytecode_end_exclusive > position.bytecode_start && nonnegative(position.source_line), `${label}[${id}]: missing row position`);
    const fieldSources = {};
    for (const [key, value] of Object.entries(fields)) {
      same(row.fields?.[key], value, `${label}[${id}].${key}`);
      const field = row.field_sources?.[key];
      requireEvidence(nonnegative(field?.bytecode_start) && field.bytecode_start >= position.bytecode_start &&
        field.bytecode_end_exclusive > field.bytecode_start && field.bytecode_end_exclusive <= position.bytecode_end_exclusive &&
        nonnegative(field.source_line) && nonnegative(field.map_assignment_offset), `${label}[${id}].${key}: missing field position`);
      fieldSources[key] = field;
    }
    projection.rows.push({ id: row.id, fields, source: position, fieldSources });
  }
  return projection;
}

function taggedTree(value) {
  if (value && (value.kind === 'integer' || value.kind === 'binary64')) return toTagged(value);
  if (Array.isArray(value)) return value.map(taggedTree);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, taggedTree(item)]));
  return value;
}

// Every numeric policy operand has an explicit integer type. AP and the divisor
// keep their binary64 types. No arbitrary expression from an APK is evaluated.
function policyScalars(value) {
  if (typeof value === 'number') return int(value);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, policyScalars(item)]));
  return value;
}

function amount(value) {
  requireEvidence(value.kind === 'integer' && compare(value, int(0)) >= 0, 'formula did not return a nonnegative integer');
  return value.value.toString();
}

function freeze(value) {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

/** A deliberately explicit reconstruction policy, not the missing RPG provider. */
export async function loadTutorialScenario(directory = DEFAULT_DIRECTORY) {
  const policyBytes = await readFile(POLICY_URL);
  const policies = JSON.parse(policyBytes);
  requireEvidence(policies.schemaVersion === 1 && policies.id === 'first-encounter-reconstruction-v1', 'unsupported policy');
  const evidence = {}, evidenceHashes = {}, tableSources = {};
  for (const [file, pin] of Object.entries(policies.sourcePins)) {
    requireEvidence(!/[\\/]/.test(file), 'source pin must be a local file name');
    const path = join(directory, file);
    let raw;
    try {
      requireEvidence((await stat(path)).size <= 32 * 1024 * 1024, `${file}: exceeds size budget`);
      raw = await readFile(path);
    } catch (error) {
      throw new Error(`Invalid tutorial evidence: required source ${file} unavailable`, { cause: error });
    }
    evidenceHashes[file] = sha(raw);
    same(evidenceHashes[file], pin.sha256, `${file}: SHA-256 mismatch`);
    const data = pin.encoding === 'text' ? raw.toString('utf8') : JSON.parse(raw);
    evidence[file] = data;
    if (pin.table) tableSources[file] = validateTable(data, pin.table, file);
    if (pin.tables) {
      tableSources[file] = {};
      for (const [name, spec] of Object.entries(pin.tables)) {
        tableSources[file][name] = validateTable(data.tables?.[name], spec, `${file}.tables.${name}`);
      }
    }
  }
  const row = (file, id) => {
    const result = evidence[file].rows.find(item => item.id === id);
    requireEvidence(result, `${file}: missing row ${id}`);
    return result;
  };
  const course = row('new-player-course.table.json', 1).fields;
  const character = row('player-character.json', course.BattleChar[0]);
  const monster = row('monster-991.json', 991);
  const baseline = evidence['player-baseline.json'];
  same(baseline.schemaVersion, 2, 'baseline requires binary64 revision');
  same(baseline.originalFinalCombatStatsRecovered, false, 'baseline recovery boundary changed');
  same(baseline.originalTutorialRarityProven, false, 'rarity is a reconstruction choice');
  same(baseline.characterId, character.id, 'baseline character');
  same(baseline.battleId, course.FirstBattleID, 'baseline battle');
  same(baseline.level, course.CharLevel[0], 'baseline level');
  same(baseline.profileId, policies.rules.playerBaseline.configuration, 'baseline policy');
  same(baseline.evidence.file, 'player-baseline.evidence.json', 'baseline evidence file');
  same(baseline.evidence.sha256, evidenceHashes[baseline.evidence.file], 'baseline evidence link');
  same(baseline.evidence.sourceApkSha256, policies.sourceApkSha256, 'baseline APK');
  same(evidence[baseline.evidence.file].sourceApkSha256, policies.sourceApkSha256, 'baseline evidence APK');
  const hp = fromTagged(baseline.baseStatsTagged?.maxHp);
  const attack = fromTagged(baseline.baseStatsTagged?.PropAtk);
  requireEvidence(hp.kind === 'binary64' && attack.kind === 'binary64' && compare(hp, int(0)) > 0 && compare(attack, int(0)) > 0,
    'baseline must provide positive, unrounded binary64 HP and attack');
  const bt = evidence['newbie_cube.xml.provenance.json'];
  same(bt.apk_sha256, policies.sourceApkSha256, 'BT APK');
  same(bt.sha256, evidenceHashes['newbie_cube.xml'], 'BT content');
  same(bt.member, 'assets/assets.npk', 'BT member');
  same(bt.index, 225, 'BT NPK entry');

  const calculations = [], conflicts = [], cards = {}, enemySkills = {};
  const states = evidence['skill-states.json'].rows;
  const orderedStates = skillId => {
    const selected = states.filter(item => item.fields.OwnerSkill === skillId).sort((a, b) => a.fields.OwnerIndex - b.fields.OwnerIndex);
    requireEvidence(selected.length > 0 && new Set(selected.map(item => item.fields.OwnerIndex)).size === selected.length,
      `skill ${skillId}: missing states or ambiguous OwnerIndex`);
    return selected;
  };
  function damage(base, extra, state, source) {
    const inputs = { ...policyScalars(policies.neutralDamage), rpgBasicActionValue: base,
      extraDamage: int(extra), dstIsPlayer: source.actor === 'enemy' };
    same(state.fields.DAMAGE_TYPE, policies.neutralDamage.rpgAttackType, `state ${state.id}: attack type`);
    const result = calcDamage(inputs);
    calculations.push({ function: 'calcDamage', stateId: state.id, source, inputs: taggedTree(inputs), trace: taggedTree(result.trace), result: toTagged(result.damage) });
    return { type: 'damage', target: policies.rules.targets.damage, amount: amount(result.damage) };
  }
  for (const card of evidence['player-cards.json'].rows) {
    const field = card.fields;
    same(field.RPG_FORMULA, [['AP']], `card ${card.id}: unsupported formula`);
    const factor = field.RPG_DEFAULT_FORMULA[0][0];
    requireEvidence(nonnegative(factor), `card ${card.id}: factor`);
    const base = classicDivide(multiply(attack, int(factor)), float(100.0));
    const effects = orderedStates(field.SKILL_ID).map(state => {
      const data = state.fields;
      if (data.STORYLINE_NAME === 'SkillState_CauseDamage') {
        if (String(factor) !== data.RPG_DEFAULT_FORMULA) conflicts.push({ kind: 'card-state-factor', cardId: String(card.id), stateId: state.id,
          cardValue: factor, originalStateValue: data.RPG_DEFAULT_FORMULA, selectedValue: factor, resolution: 'explicit card-table reconstruction policy; original provider unknown' });
        return damage(base, data.STORYLINE_PARAM['#EXTRA_DAMAGE'], state, {
          kind: 'reconstruction-resolved-input', actor: 'player', cardId: String(card.id),
          baseResolution: { policy: 'playerBaseDamage', attack: toTagged(attack), factor: toTagged(int(factor)), divisor: toTagged(float(100.0)), value: toTagged(base) },
          extraDamageField: 'skill_state_table.STORYLINE_PARAM.#EXTRA_DAMAGE', neutralPolicy: 'neutralDamage', providerRecovered: false,
        });
      }
      requireEvidence(card.id === 410102 && state.id === 367 && data.STORYLINE_NAME === 'SkillState_getCard', `unsupported player state ${state.id}`);
      const count = field.SKILL_DIY_VALUE[field.SKILL_DIY_PARAMETER.indexOf('VALUE')];
      same(count, policies.rules.card410102Draw.value, 'draw override');
      same(data.STORYLINE_PARAM.VALUE, policies.rules.card410102Draw.originalStateValue, 'draw source conflict');
      conflicts.push({ kind: 'card-state-draw', cardId: String(card.id), stateId: state.id, cardValue: count,
        originalStateValue: data.STORYLINE_PARAM.VALUE, selectedValue: count, resolution: 'explicit DIY VALUE override; original provider unknown' });
      return { type: 'draw', count };
    });
    cards[String(card.id)] = { name: field.NAME, cost: field.COST, effects };
  }
  for (const skillId of [990, 991, 992]) {
    const effects = orderedStates(skillId).map(state => {
      const data = state.fields;
      requireEvidence(!Object.hasOwn(data, 'RPG_FORMULA') && !Object.hasOwn(data, 'RPG_DEFAULT_FORMULA'), `state ${state.id}: expected absent RPG fields`);
      const missingBase = int(policies.rules.monsterMissingRpgBase.value);
      if (data.STORYLINE_NAME === 'SkillState_MonsterCauseDamage') {
        same(data.DATA.TIMES, 1, 'unsupported monster repeat');
        return damage(missingBase, data.STORYLINE_PARAM.VALUE, state, { kind: 'reconstruction-resolved-input', actor: 'enemy', skillId: String(skillId),
          baseResolution: { policy: 'monsterMissingRpgBase', value: toTagged(missingBase), missingFields: ['RPG_FORMULA', 'RPG_DEFAULT_FORMULA'] },
          extraDamageField: 'skill_state_table.STORYLINE_PARAM.VALUE', neutralPolicy: 'neutralDamage', providerRecovered: false });
      }
      requireEvidence(skillId === 992 && data.STORYLINE_NAME === 'SkillState_AddShield', `unsupported enemy state ${state.id}`);
      // 300 + explicit zero; card=null also preserves the known original helper binding issue.
      const stateValue = int(data.STORYLINE_PARAM.VALUE);
      const basicBlock = add(stateValue, missingBase);
      same(missingBase.value.toString(), '0', 'shield missing RPG base policy');
      const inputs = { ...policyScalars(policies.neutralShield), basicBlock };
      const result = calcBlock(inputs);
      calculations.push({ function: 'calcBlock', stateId: state.id, source: { kind: 'reconstruction-resolved-input', actor: 'enemy', skillId: String(skillId),
        baseResolution: { expression: 'STORYLINE_PARAM.VALUE + explicit missing RPG base 0', stateValue: toTagged(stateValue), missingRpgBase: toTagged(missingBase) },
        neutralPolicy: 'neutralShield', providerRecovered: false }, inputs: taggedTree(inputs), trace: taggedTree(result.trace), result: toTagged(result.block) });
      return { type: 'shield', target: policies.rules.targets.shield, amount: amount(result.block) };
    });
    enemySkills[String(skillId)] = { effects };
  }
  const limits = policies.rules.limits;
  const definition = {
    player: { id: String(character.id), name: character.fields.NAME, maxHp: toTagged(hp) },
    enemy: { id: String(monster.id), name: monster.fields.NAME, maxHp: toTagged(int(monster.fields.enforce_maxHp)) },
    deck: course.CardPile.map(([cardId, ownerCharacterId], index) => {
      requireEvidence(cards[String(cardId)] && ownerCharacterId === character.id && ownerCharacterId === course.BattleChar[0],
        `deck card ${cardId} missing or owner character mismatch`);
      return { instanceId: `tutorial-card-${index + 1}`, cardId: String(cardId) };
    }),
    cards, enemySkills, enemyIntents: policies.rules.enemyTurns.intentions, enemyFallback: policies.rules.enemyTurns.fallback,
    initialDraw: limits.initialDraw, roundDraw: limits.roundDraw, energyPerRound: limits.energyPerRound, handLimit: limits.handLimit, maxRounds: limits.maxRounds,
  };
  const codeHashes = {};
  for (const relative of ['./tutorial.js', '../../packages/battle-core/src/index.js', '../../packages/battle-core/src/numeric.js', '../../packages/battle-core/src/tables.js', '../../packages/battle-session/src/index.js']) {
    codeHashes[relative] = sha(await readFile(new URL(relative, import.meta.url)));
  }
  const policySha256 = sha(policyBytes);
  const evidenceSha256 = sha(JSON.stringify(evidenceHashes));
  const ruleEvidenceHash = sha(JSON.stringify({ policySha256, evidenceSha256, codeHashes, definition }));
  definition.id = `tutorial-5000-${ruleEvidenceHash}`;
  validateDefinition(definition);
  return freeze({ definition, title: policies.title, notice: policies.notice, policies, provenance: {
    kind: 'explicit-reconstruction-with-static-evidence', statsRecovered: false, originalRpgProviderRecovered: false,
    sourceApkSha256: policies.sourceApkSha256, policySha256, evidenceSha256, ruleEvidenceHash, codeHashes, evidenceHashes,
    verification: 'Pinned exported evidence bytes, original module identities, row literals and field positions checked; APK/runtime not executed or rehashed by this loader.',
    tables: tableSources, behaviorTree: bt, baseline, formulaSource: policies.formulaSource, calculations, conflicts,
    deckOwnership: course.CardPile.map(([cardId, ownerCharacterId], index) => ({ instanceId: definition.deck[index].instanceId, cardId: String(cardId), ownerCharacterId: String(ownerCharacterId) })),
  } });
}
