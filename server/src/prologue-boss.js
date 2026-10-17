import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { fromTagged, toTagged, int, float, compare } from '../../packages/battle-core/src/index.js';
import { validateDefinition, PARTY_POLICY } from '../../packages/battle-session/src/index.js';
import { prologueBossIntention, prologueBossLimits } from './prologue-source-rules.js';

const DEFAULT_DIRECTORY = fileURLToPath(new URL('../../analysis/prologue-boss/', import.meta.url));
const POLICY_URL = new URL('../data/prologue-boss-policy.json', import.meta.url);
const sha = value => createHash('sha256').update(value).digest('hex');
const requireEvidence = (condition, message) => { if (!condition) throw new Error(`Invalid prologue boss evidence: ${message}`); };
const same = (actual, expected, label) => requireEvidence(isDeepStrictEqual(actual, expected), label);
const TABLES = {
  'course.json': 'common\\cdata\\new_player_course_table.py',
  'cards.json': 'common\\cdata\\card_table.py',
  'skill-states.json': 'common\\cdata\\skill_state_table.py',
  'enemy-skills.json': 'common\\cdata\\skill_table.py',
  'monster.json': 'common\\cdata\\monster_table.py',
  'battle.json': 'common\\cdata\\maze_battle_table_2.py',
  'referenced-buffs.json': 'common\\cdata\\buff_table.py',
  'characters.json': 'common\\cdata\\character_basic_info.py',
};
function freeze(value) {
  if (value && typeof value === 'object') { for (const child of Object.values(value)) freeze(child); Object.freeze(value); }
  return value;
}

/** Battle 1703 with labelled reconstruction rules; the original resolvers are not recovered. */
export async function loadPrologueBossScenario(directory = DEFAULT_DIRECTORY) {
  const policyBytes = await readFile(POLICY_URL);
  const policies = JSON.parse(policyBytes);
  requireEvidence(policies.schemaVersion === 1 && policies.id === 'prologue-boss-1703-reconstruction-v1', 'unsupported policy');
  const evidence = {}, evidenceHashes = {};
  for (const [file, pin] of Object.entries(policies.sourcePins)) {
    requireEvidence(!/[\\/]/.test(file), 'source pin must be a local file name');
    let raw;
    try {
      requireEvidence((await stat(join(directory, file))).size <= 32 * 1024 * 1024, `${file}: exceeds size budget`);
      raw = await readFile(join(directory, file));
    } catch (error) {
      throw new Error(`Invalid prologue boss evidence: required source ${file} unavailable`, { cause: error });
    }
    evidenceHashes[file] = sha(raw);
    same(evidenceHashes[file], pin, `${file}: SHA-256 mismatch`);
    evidence[file] = JSON.parse(raw);
    if (TABLES[file]) same(evidence[file].source?.filename, TABLES[file], `${file}: source module`);
  }
  const rows = file => new Map(evidence[file].rows.map(row => [row.id, row.fields]));
  const row = (file, rowId) => {
    const result = rows(file).get(rowId);
    requireEvidence(result, `${file}: missing row ${rowId}`);
    return result;
  };
  const course = row('course.json', policies.rules.party.courseRow);
  same([course.FirstBattleID, course.BattleChar, course.CharLevel, course.DisableSpecialSkill, course.EnableSpecialSkillRound],
    [prologueBossLimits.battleId, [1, 3], [100, 100], true, 2], 'course row 2');
  const battle = row('battle.json', course.FirstBattleID);
  same(battle.MonsterInfo, [{ MonsterID: prologueBossLimits.monsterId, SpawnPointIdx: 0 }], 'battle monster');
  same(battle.MaxRoundFail, prologueBossLimits.maxRoundFail, 'MaxRoundFail');
  const monster = row('monster.json', prologueBossLimits.monsterId);
  same([monster.BT_PATH, monster.enforce_maxHp, monster.enforce_PropAtk], ['xinshou_zhongyanshizhe.xml', 10000, 180.0], 'monster 2013');
  const buffRow = row('referenced-buffs.json', Number(policies.rules.attackBuff.buffId));
  same([buffRow.DESCRIPTION_INDEX, buffRow.BUFF_MAX, buffRow.NEED_TIME, buffRow.IS_BENEFITBUFF], ['%s*6', 999, false, true], 'buff 1001');

  const baseline = evidence['party-baseline.json'];
  same([baseline.schemaVersion, baseline.profileId, baseline.battleId, baseline.originalFinalCombatStatsRecovered],
    [1, policies.rules.partyBaseline.configuration, course.FirstBattleID, false], 'party baseline profile');
  same(baseline.evidence.sha256, evidenceHashes['party-baseline.evidence.json'], 'party baseline evidence link');
  same(baseline.evidence.sourceApkSha256, policies.sourceApkSha256, 'party baseline APK');
  const party = course.BattleChar.map((characterId, index) => {
    const character = row('characters.json', characterId), member = baseline.members[index];
    same([member.characterId, member.name, member.level, member.formationIndex], [characterId, character.NAME, course.CharLevel[index], index], `member ${characterId}`);
    const maxHp = fromTagged(member.baseStatsTagged.maxHp), attack = fromTagged(member.baseStatsTagged.PropAtk);
    requireEvidence(maxHp.kind === 'binary64' && attack.kind === 'binary64' && compare(maxHp, int(0)) > 0 && compare(attack, int(0)) > 0, 'member stats');
    return { id: String(characterId), name: character.NAME, maxHp: toTagged(maxHp), attack: toTagged(attack) };
  });
  same(baseline.members.length, party.length, 'party baseline size');

  const states = evidence['skill-states.json'].rows;
  const orderedStates = skillId => {
    const selected = states.filter(item => item.fields.OwnerSkill === skillId).sort((a, b) => a.fields.OwnerIndex - b.fields.OwnerIndex);
    requireEvidence(selected.length && new Set(selected.map(item => item.fields.OwnerIndex)).size === selected.length, `skill ${skillId}: states`);
    return selected;
  };
  const conflicts = [], cards = {};
  for (const [cardId, field] of rows('cards.json')) {
    const factorFormula = field.RPG_DEFAULT_FORMULA?.[0]?.[0];
    const diyValue = field.SKILL_DIY_PARAMETER?.includes('VALUE') ? field.SKILL_DIY_VALUE[field.SKILL_DIY_PARAMETER.indexOf('VALUE')] : undefined;
    const effects = orderedStates(field.SKILL_ID).map(({ id: stateId, fields: s }) => {
      const factor = () => {
        requireEvidence(Number.isSafeInteger(factorFormula) && factorFormula >= 0, `card ${cardId}: factor`);
        if (s.RPG_DEFAULT_FORMULA !== undefined && String(factorFormula) !== String(s.RPG_DEFAULT_FORMULA))
          conflicts.push({ kind: 'card-state-factor', cardId: String(cardId), stateId, cardValue: factorFormula,
            originalStateValue: s.RPG_DEFAULT_FORMULA, selectedValue: factorFormula, resolution: 'card-table reconstruction policy' });
        return factorFormula;
      };
      if (s.STORYLINE_NAME === 'SkillState_CauseDamage') {
        same([s.SKILL_STATE_TARGET_TYPE, s.SKILL_STATE_CAMP_TYPE, field.RPG_FORMULA], [16, 0, [['AP']]], `state ${stateId}: damage target`);
        return { type: 'damage', target: 'opponent', factor: factor() };
      }
      if (s.STORYLINE_NAME === 'SkillState_AddShield') {
        requireEvidence(s.SKILL_STATE_CAMP_TYPE === 1 && [16, 17].includes(s.SKILL_STATE_TARGET_TYPE) && isDeepStrictEqual(field.RPG_FORMULA, [['APSHD']]), `state ${stateId}: shield`);
        return { type: 'shield', target: s.SKILL_STATE_TARGET_TYPE === 17 ? 'party' : 'self', factor: factor() };
      }
      if (s.STORYLINE_NAME === 'SkillState_TargetAddBuff') {
        same([s.SKILL_STATE_TARGET_TYPE, s.SKILL_STATE_CAMP_TYPE, String(s.STORYLINE_PARAM.BUFF_ID)], [17, 1, policies.rules.attackBuff.buffId], `state ${stateId}: buff`);
        return { type: 'attackBuff', target: 'party', stacks: s.STORYLINE_PARAM.BUFF_NUM };
      }
      requireEvidence(s.STORYLINE_NAME === 'SkillState_getCard' && Number.isSafeInteger(s.STORYLINE_PARAM.VALUE), `unsupported player state ${stateId}`);
      if (diyValue !== undefined && diyValue !== s.STORYLINE_PARAM.VALUE)
        conflicts.push({ kind: 'card-state-draw', cardId: String(cardId), stateId, cardValue: diyValue,
          originalStateValue: s.STORYLINE_PARAM.VALUE, selectedValue: diyValue, resolution: 'card DIY VALUE override' });
      return { type: 'draw', count: diyValue ?? s.STORYLINE_PARAM.VALUE };
    });
    cards[String(cardId)] = { name: field.NAME, cost: field.COST, effects };
  }
  const enemySkills = {};
  for (const [skillId] of rows('enemy-skills.json')) {
    enemySkills[String(skillId)] = { effects: orderedStates(skillId).map(({ id: stateId, fields: s }) => {
      if (s.STORYLINE_NAME === 'SkillState_SelfAddBuff') {
        same(String(s.STORYLINE_PARAM.BUFF_ID), policies.rules.attackBuff.buffId, `state ${stateId}: boss buff`);
        return { type: 'attackBuff', target: 'self', stacks: s.STORYLINE_PARAM.BUFF_NUM };
      }
      same([s.STORYLINE_NAME, s.SKILL_STATE_TARGET_TYPE, s.RPG_FORMULA, s.STORYLINE_PARAM.VALUE], ['SkillState_MonsterCauseDamage', 9, 'PropAtk', 0], `state ${stateId}: boss damage`);
      const factor = Number(s.RPG_DEFAULT_FORMULA);
      requireEvidence(Number.isSafeInteger(factor) && String(factor) === String(s.RPG_DEFAULT_FORMULA), `state ${stateId}: factor`);
      return { type: 'damage', target: 'first-mid-last', factor, times: s.DATA.TIMES };
    }) };
  }
  const limits = policies.rules.limits;
  const maxRounds = battle.MaxRoundFail;
  const definition = {
    player: { id: 'party-1-3', name: party.map(member => member.name).join(' · ') },
    party,
    enemy: { id: String(prologueBossLimits.monsterId), name: monster.NAME, maxHp: toTagged(int(monster.enforce_maxHp)), attack: toTagged(float(monster.enforce_PropAtk)) },
    deck: course.CardPile.map(([cardId, ownerId], index) => {
      requireEvidence(cards[String(cardId)] && course.BattleChar.includes(ownerId), `deck card ${cardId} owner ${ownerId}`);
      return { instanceId: `boss-card-${index + 1}`, cardId: String(cardId), ownerId: String(ownerId) };
    }),
    cards, enemySkills,
    enemyIntents: Array.from({ length: maxRounds }, (_, index) => [String(prologueBossIntention(index + 1))]),
    enemyFallback: [String(prologueBossIntention(maxRounds))],
    initialDraw: limits.initialDraw, roundDraw: limits.roundDraw, energyPerRound: limits.energyPerRound, handLimit: limits.handLimit, maxRounds,
    partyRules: { policy: PARTY_POLICY, buffId: policies.rules.attackBuff.buffId, attackPercentPerStack: policies.rules.attackBuff.attackPercentPerStack,
      maxStacks: policies.rules.attackBuff.maxStacks, enemyTargeting: 'first-living-in-formation' },
  };
  const codeHashes = {};
  for (const relative of ['./prologue-boss.js', './prologue-source-rules.js', '../../packages/battle-core/src/index.js',
    '../../packages/battle-core/src/numeric.js', '../../packages/battle-session/src/party.js']) {
    codeHashes[relative] = sha(await readFile(new URL(relative, import.meta.url)));
  }
  const policySha256 = sha(policyBytes), evidenceSha256 = sha(JSON.stringify(evidenceHashes));
  const ruleEvidenceHash = sha(JSON.stringify({ policySha256, evidenceSha256, codeHashes, definition }));
  definition.id = `prologue-boss-1703-${ruleEvidenceHash}`;
  validateDefinition(definition);
  return freeze({ definition, title: policies.title, notice: policies.notice, policies, provenance: {
    kind: 'explicit-reconstruction-with-static-evidence', statsRecovered: false, originalRpgProviderRecovered: false,
    targetResolverRecovered: false, sourceApkSha256: policies.sourceApkSha256, policySha256, evidenceSha256, ruleEvidenceHash,
    codeHashes, evidenceHashes, conflicts,
    verification: 'Pinned exported evidence bytes, original module identities and row literals checked; APK/runtime not executed by this loader.',
  } });
}
