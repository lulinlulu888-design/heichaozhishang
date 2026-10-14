import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { int, float, toTagged, fromTagged, monsterProperty, multiply, classicDivide, calcDamage, calcBlock } from '../../packages/battle-core/src/index.js';
import { validateDefinition } from '../../packages/battle-session/src/index.js';
import { weightedIntents } from './weighted-intents.js';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const scalarTree = value => typeof value === 'number' ? int(value) :
  value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).map(([k,v]) => [k, scalarTree(v)])) : value;
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };

/** Explicit local context over recovered source tables; no claim of original server compatibility. */
export async function loadCityScenario(base) {
  if (!base?.provenance?.baseline) throw new Error('City preview requires verified tutorial baseline');
  const rawPolicy = await readFile(new URL('../data/city-preview-policy.json', import.meta.url));
  const policy = JSON.parse(rawPolicy);
  if (policy.format !== 'hczs-city-preview-v1' || policy.encounter !== 10405 || policy.monster !== 6605 ||
      !Number.isInteger(policy.level) || policy.level < 1 || policy.level > 400 || policy.maxRounds !== 30) throw new Error('Invalid city policy');
  const evidence = {};
  for (const name of ['monster-properties', 'battle-skills']) {
    const raw = await readFile(new URL(`../../analysis/battle-visual/city-scenes/${name}/report.json`, import.meta.url));
    if (sha(raw) !== policy.sourcePins[name]) throw new Error('City evidence hash mismatch: ' + name);
    evidence[name] = JSON.parse(raw);
  }
  const props = evidence['monster-properties'], skills = evidence['battle-skills'];
  const m = props.monster.rows.find(r => r.id === policy.monster)?.fields;
  const curve = props.curve.rows.find(r => r.fields.Math_model === m?.Math_model && r.fields.Level === policy.level)?.fields;
  if (!curve || m.Math_model !== 'elite') throw new Error('Missing city level curve');
  const resolved = (name, ratioKey) => monsterProperty({
    forced: Object.hasOwn(m, 'enforce_' + name) ? float(m['enforce_' + name]) : null,
    base: name === 'maxHp' ? int(curve[name]) : float(curve[name]),
    monsterRatio: float(m[ratioKey] ?? 1), mazeRatio: float(1), challengeRatio: int(1),
  });
  const hp = resolved('maxHp', 'HP_modify_ratio'), attack = resolved('PropAtk', 'ATK_modify_ratio');
  const definition = structuredClone(base.definition);
  definition.enemy = { id: '6605', name: '比克卢', maxHp: toTagged(hp) };
  definition.enemySkills = {};
  const calculations = [];
  for (const row of skills.tables.states.rows) {
    const s = row.fields, id = String(s.OwnerSkill);
    let effects;
    if (s.STORYLINE_NAME === 'SkillState_MonsterCauseDamage') {
      if (s.RPG_FORMULA !== 'PropAtk' || ![1,2].includes(s.DATA.TIMES) || s.STORYLINE_PARAM.VALUE !== 0) throw new Error('Unsupported city damage');
      const basic = classicDivide(multiply(attack, int(s.RPG_DEFAULT_FORMULA)), float(100));
      const result = calcDamage({ ...scalarTree(base.policies.neutralDamage), rpgAttackType: int(s.DAMAGE_TYPE),
        rpgBasicActionValue: basic, extraDamage: int(0), dstIsPlayer: true });
      effects = Array.from({length:s.DATA.TIMES}, () => ({type:'damage',target:'opponent',amount:result.damage.value.toString()}));
      calculations.push({skillId:id, base:toTagged(basic), result:toTagged(result.damage), times:s.DATA.TIMES});
    } else if (s.STORYLINE_NAME === 'SkillState_AddShield') {
      if (s.RPG_FORMULA !== 'maxHp' || s.STORYLINE_PARAM.VALUE !== 0) throw new Error('Unsupported city shield');
      const basic = classicDivide(multiply(hp, int(s.RPG_DEFAULT_FORMULA)), float(100));
      const result = calcBlock({...scalarTree(base.policies.neutralShield),basicBlock:basic});
      effects = [{type:'shield',target:'self',amount:result.block.value.toString()}];
      calculations.push({skillId:id,base:toTagged(basic),result:toTagged(result.block)});
    } else {
      if (s.STORYLINE_NAME !== 'SkillState_TargetAddBuff' || s.STORYLINE_PARAM.BUFF_ID !== 66051 || s.STORYLINE_PARAM.BUFF_NUM !== 2) throw new Error('Unsupported city buff');
      effects = [{type:'breakdown',target:'opponent',stacks:2}];
    }
    if (Object.hasOwn(definition.enemySkills,id)) throw new Error('Duplicate city skill state');
    definition.enemySkills[id] = { effects };
  }
  if (Object.keys(definition.enemySkills).sort().join(',') !== '66051,66052,66053,66054') throw new Error('Incomplete city skills');
  const enemySelection = { algorithm:'sha256-weighted-intents-v1', divisor:3, remainder:1, fixedSkill:'66054',
    pool:m.RANDOM_SKILL_IDS.map(row => ({skillId:String(row.SKILL_ID),weight:row.WEIGHT})) };
  // Template endpoint uses seed0 only; BattleStore materializes each newly created battle.
  definition.enemyIntents = weightedIntents(enemySelection, 0, policy.maxRounds);
  definition.enemyFallback = ['66054']; definition.maxRounds = policy.maxRounds;
  definition.statusRules = { policy:'breakdown-reconstruction-v1', attack:{
    player:toTagged(fromTagged(base.provenance.baseline.baseStatsTagged.PropAtk)), enemy:toTagged(attack) } };
  const loaderSha256 = sha(await readFile(new URL('./city-scenario.js', import.meta.url)));
  const selectionSha256 = sha(await readFile(new URL('./weighted-intents.js', import.meta.url)));
  const contentHash = sha(JSON.stringify({policy,definition,loaderSha256,selectionSha256,base:base.definition.id}));
  definition.id = 'city-preview-10405-' + contentHash;
  validateDefinition(definition);
  return freeze({definition,title:'城市试战 · 比克卢',notice:'本地40级重建试玩，非原服关卡数值。',
    policies:{mode:'city-reconstruction-preview', ...policy, enemySelection},
    provenance:{mode:'city-reconstruction-preview',originalScenarioRecovered:false,sourceEncounter:10405,
      sourcePins:policy.sourcePins,policySha256:sha(rawPolicy),loaderSha256,selectionSha256,contentHash,
      baselineDefinitionId:base.definition.id,level:policy.level,monsterHp:toTagged(hp),monsterAttack:toTagged(attack),calculations}});
}
