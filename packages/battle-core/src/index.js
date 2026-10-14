import {
  int, float, scalar, add, subtract, multiply, classicDivide, truncate, compare, maximum,
} from './numeric.js';
export {
  int, float, fromTagged, toTagged, assertNumericRuntime, add, subtract, multiply,
  classicDivide, truncate, compare,
} from './numeric.js';
export { RECOVERED_COUNTER_TABLE } from './tables.js';

const I = int, F = float;
const zero = I(0), one = I(1);

/** combatUtils 3510:70/74/81/82 after table/context resolution.
 * A non-None forced value (including zero) bypasses base and ratio reads.
 */
export function monsterProperty(input) {
  const forced = field(input, 'forced');
  if (forced !== null) return scalar(forced, 'forced');
  let value = number(input, 'base');
  for (const key of ['monsterRatio', 'mazeRatio', 'challengeRatio']) value = multiply(value, number(input, key));
  return value;
}

/** 2905:147.8 GetRpgProps scalar projection after resolving the property.
 * method 0 floors, 1 ceils, other integer values leave the binary64 unchanged.
 * This is an extra-damage input for MB_breakdown, not final HP loss.
 */
export function rpgPropertyPercent(input) {
  const method = field(input, 'method');
  if (!Number.isSafeInteger(method)) throw new TypeError('method requires an integer');
  const value = classicDivide(multiply(number(input, 'property'), number(input, 'percent')), F(100));
  if (method === 0) return int(BigInt(Math.floor(value.value)));
  if (method === 1) return int(BigInt(Math.ceil(value.value)));
  return value;
}

function field(input, key) {
  if (!input || !Object.prototype.hasOwnProperty.call(input, key)) throw new TypeError(`missing dependency: ${key}`);
  return input[key];
}
const number = (input, key) => scalar(field(input, key), key);
function flag(input, key) {
  const value = field(input, key);
  if (typeof value !== 'boolean') throw new TypeError(`${key} requires a boolean`);
  return value;
}
function list(input, key) {
  const value = field(input, key);
  if (!Array.isArray(value)) throw new TypeError(`${key} requires an ordered scalar array`);
  return value.map(item => scalar(item, key));
}

/** common/formula.py 7042:7. Pure, resolved snapshot, not card/HP resolution. */
export function calcDamage(input) {
  const trace = [];
  const record = (stage, value) => { trace.push(Object.freeze({ stage, value })); return value; };
  const attackType = number(input, 'rpgAttackType');
  let value = record('base_and_add', add(number(input, 'rpgBasicActionValue'), number(input, 'addAttackValue')));
  if (compare(attackType, I(3)) !== 0) {
    value = record('counter', multiply(value, number(input, 'combatCounterRatioValue')));
    value = record('defense', multiply(value, number(input, 'dstEntityDefenseValue')));
    let buff = add(add(one, number(input, 'attackFactorValue')), number(input, 'attackedFactorValue'));
    if (flag(input, 'dstIsPlayer')) buff = maximum(subtract(one, F(0.9)), buff);
    value = record('buff', multiply(value, buff));
    value = record('critical', multiply(value, number(input, 'criticalRatioValue')));
  }
  let ratio = subtract(add(one, number(input, 'propDamageIncValue')), number(input, 'propDamageReduceValue'));
  if (compare(attackType, I(1)) === 0) {
    ratio = add(ratio, subtract(number(input, 'propAtkDamageIncValue'), number(input, 'propAtkDamageReduceValue')));
  } else if (compare(attackType, I(2)) === 0) {
    ratio = add(ratio, subtract(number(input, 'propMgcDamageIncValue'), number(input, 'propMgcDamageReduceValue')));
  }
  value = record('damage_properties', multiply(value, ratio));
  value = record('overwhelm', multiply(value, number(input, 'overwhelmRatio')));
  value = record('extra_attack', add(value, number(input, 'extraAttackValue')));
  value = record('extra_attacked', add(value, number(input, 'extraAttackedValue')));
  value = record('extra_damage', add(value, number(input, 'extraDamage')));
  if (flag(input, 'isPVP')) value = record('pvp', multiply(value, number(input, 'pvpAtkRatio')));
  if (flag(input, 'isDamageSkillPreview')) value = record('preview_slow_hp', subtract(value, number(input, 'slowHp')));
  if (compare(value, one) <= 0) value = one;
  record('clamped', value);
  return Object.freeze({ damage: truncate(value), trace: Object.freeze(trace) });
}

/** 7042:11. Resolved entity/card dependencies; does not apply shield to HP. */
export function calcBlock(input) {
  const source = field(input, 'source'), card = field(input, 'card'), target = field(input, 'target');
  for (const [name, object] of [['source', source], ['card', card], ['target', target]]) {
    if ((object === null && name !== 'target')) continue;
    if (!object || typeof object !== 'object' || Array.isArray(object)) {
      throw new TypeError(`${name} requires a resolved dependency object${name === 'target' ? '' : ' or explicit null'}`);
    }
  }
  const trace = [];
  const record = (stage, value) => { trace.push(Object.freeze({ stage, value })); return value; };
  let value = number(input, 'basicBlock');
  // Source 7042:11 calls helper(basicBlock, srcEntity, cardObj), but the
  // helper's signature is (basicValue, srcEntity, strengthFactor=None,
  // cardObj=None). Thus its cardObj remains None and it returns basicBlock.
  // Do not repair this apparent shipped call-site bug by applying improvement.
  record('base', value);
  if (source !== null) {
    value = record('source_property', multiply(value,
      add(one, classicDivide(number(source, 'propAddTargetShield'), F(1000)))));
  }
  // calcBlock later unconditionally dereferences dstEntity.battleInst.
  // The successful-call contract therefore requires an actual target.
  value = record('target_property', multiply(value,
    add(one, classicDivide(number(target, 'propBeAddShield'), F(1000)))));
  let ratio = add(add(one, source === null ? zero : number(source, 'shieldFactor')),
    number(target, 'shieldFactor'));
  ratio = add(ratio, card === null ? zero : classicDivide(number(card, 'extraBaseBlockPercent'), F(100)));
  value = record('shield_factors', multiply(value, ratio));
  value = record('additional_block', add(value, card === null ? zero : number(card, 'additionalBlockValue')));
  if (flag(target, 'isPVP')) value = record('pvp', multiply(value, number(target, 'pvpShieldRatio')));
  // max(0, value), zero FIRST: zero ties retain integer zero, including -0.0.
  value = record('clamped', maximum(zero, value));
  return Object.freeze({ block: truncate(value), trace: Object.freeze(trace) });
}

/** 7042:8. lvDiff is the already resolved original source/destination difference. */
export function overwhelmRatio(input) {
  if (flag(input, 'disabled')) return one;
  const sp = flag(input, 'srcIsPlayer'), dp = flag(input, 'dstIsPlayer');
  const level = number(input, 'lvDiff');
  let ratio = zero;
  if (sp && !dp) {
    if (compare(level, I(5)) < 0) ratio = zero;
    else if (compare(level, I(15)) <= 0) {
      ratio = add(F(0.02), multiply(multiply(multiply(F(0.5), subtract(level, I(5))), subtract(level, I(4))), F(0.015)));
    } else ratio = one;
  } else if (!sp && dp) {
    if (compare(level, I(4)) <= 0) ratio = zero;
    else if (compare(level, I(9)) <= 0) ratio = F(0.5);
    else if (compare(level, I(15)) < 0) ratio = F(1.5);
    else if (compare(level, I(30)) <= 0) ratio = add(I(2), multiply(F(0.2), subtract(level, I(15))));
    else ratio = I(5);
  }
  if (sp && dp) ratio = zero;
  else if (!sp && !dp) {
    if (compare(level, I(3)) <= 0) ratio = zero;
    else if (compare(level, I(30)) > 0) ratio = I(2);
    else ratio = multiply(multiply(multiply(F(0.5), subtract(level, I(2))), subtract(level, I(3))), F(0.005));
  }
  return add(one, maximum(zero, ratio));
}

/** 3510:27/28. Missing source row/ratio defaults below are proved table rules. */
export function counterRatio(input) {
  const dst = number(input, 'dstType');
  if (flag(input, 'allCounter')) {
    return compare(dst, I(7)) === 0 ? F(1) : classicDivide(number(input, 'allRatio'), F(100));
  }
  const src = number(input, 'srcType');
  if (src.kind !== 'integer' || dst.kind !== 'integer') throw new TypeError('counter type IDs require integers');
  const table = field(input, 'table');
  if (!table || typeof table !== 'object' || Array.isArray(table)) throw new TypeError('counter table required');
  let ratio = I(100);
  const key = src.value.toString();
  if (Object.prototype.hasOwnProperty.call(table, key)) {
    const row = table[key];
    if (!row || typeof row !== 'object') throw new TypeError('invalid counter table row');
    if (Object.prototype.hasOwnProperty.call(row, 'beCounterID') && compare(scalar(row.beCounterID), dst) === 0) {
      ratio = Object.prototype.hasOwnProperty.call(row, 'beCounterRatio') ? scalar(row.beCounterRatio) : I(100);
    }
    // Deliberately a second IF: counter overrides beCounter for rows 5 and 6.
    if (Object.prototype.hasOwnProperty.call(row, 'counterID') && compare(scalar(row.counterID), dst) === 0) {
      ratio = Object.prototype.hasOwnProperty.call(row, 'counterRatio') ? scalar(row.counterRatio) : I(100);
    }
  }
  return classicDivide(ratio, F(100));
}

/** 7042:9. The caller has already selected physical/magic defense. */
export function defenseRatio(input) {
  const attack = number(input, 'attack');
  if (compare(attack, zero) === 0) return zero;
  const reduced = maximum(subtract(number(input, 'defense'), number(input, 'penetration')), zero);
  return classicDivide(attack, add(attack, multiply(reduced, I(5))));
}

/** 7042:10. null explicitly means no matched improvement; undefined is missing. */
export function basicActionValue(input) {
  const basic = number(input, 'basicDamage');
  const improvement = field(input, 'improvement');
  if (improvement === null) return basic;
  return add(basic, add(multiply(number(improvement, 'factor'), number(improvement, 'property')), number(improvement, 'base')));
}

/** 7554:5.0. A proved intermediate int() truncation, before the outer sum. */
export function addAttackValue(input) {
  const extra = truncate(multiply(number(input, 'rpgBasicActionValue'),
    classicDivide(number(input, 'extraBaseDamagePercent'), F(100))));
  return add(add(number(input, 'cardAdditionalValue'), number(input, 'entityAttackAddValue')), extra);
}

/** 7554:5.9/5.4. Arrays retain the caller's observed iteration order. */
export function attackFactorValue(input) {
  let value = zero;
  for (const factor of list(input, 'factors')) value = add(value, subtract(factor, one));
  for (const common of list(input, 'commonFactors')) value = add(value, subtract(common, one));
  value = add(zero, value); // Outer rpgGetAttackFactorValue starts with integer zero.
  return add(add(value, number(input, 'cardFactor')), number(input, 'battleFactor'));
}

/** 7554:5.8/5.5. Attacked common factors use /100.0, unlike attack common factors. */
export function attackedFactorValue(input) {
  let value = zero;
  for (const factor of list(input, 'factors')) value = add(value, subtract(factor, one));
  for (const common of list(input, 'commonFactors')) value = add(value, classicDivide(common, F(100)));
  value = add(zero, value); // Outer rpgGetAttackedFactorValue starts with integer zero.
  if (!flag(input, 'excluded')) value = subtract(value, classicDivide(number(input, 'reduceDamagedRate'), F(100)));
  return value;
}

/** 7554:5.12/13/14. Property-name mapping is deliberately resolved by caller. */
export function propertyValue(input) {
  let value = number(input, 'base');
  for (const modifier of list(input, 'modifiers')) value = add(value, modifier);
  // 7554:5.13 offsets 87..99: max(0, res), retaining the first operand on ties.
  return flag(input, 'isPropAtk') ? maximum(zero, value) : value;
}

/** 7042:4. Supplied draw only; no RNG or substitution for calcDamage's card path. */
export function criticalOutcome(input) {
  const critical = classicDivide(maximum(zero, subtract(number(input, 'srcCritical'), number(input, 'defendCritical'))), F(1000));
  const block = classicDivide(number(input, 'blockProperty'), F(1000));
  const upper = maximum(add(critical, block), F(1));
  const draw = number(input, 'draw');
  if (compare(draw, zero) < 0 || compare(draw, upper) > 0) throw new RangeError('draw outside source interval');
  if (compare(draw, critical) <= 0) {
    return Object.freeze({ kind: I(1), ratio: add(number(input, 'srcCriticalDamage'), number(input, 'cardExtra')) });
  }
  if (compare(draw, add(critical, block)) <= 0) {
    return Object.freeze({ kind: I(2), ratio: subtract(F(1), number(input, 'blockDamageProperty')) });
  }
  return Object.freeze({ kind: zero, ratio: F(1) });
}
