import {
  int, float, calcDamage, defenseRatio, toTagged, fromTagged,
  RECOVERED_COUNTER_TABLE, counterRatio, rpgPropertyPercent, monsterProperty,
} from '../src/index.js';
import type { DamageSnapshot } from '../src/index.js';

const snapshot: DamageSnapshot = {
  rpgAttackType: int(3), rpgBasicActionValue: int('9007199254740993'),
  addAttackValue: int(0), propDamageIncValue: int(0), propDamageReduceValue: int(0),
  overwhelmRatio: int(1), extraAttackValue: int(0), extraAttackedValue: int(0),
  extraDamage: int(0), isPVP: false, isDamageSkillPreview: false,
};
const exact: bigint = calcDamage(snapshot).damage.value;
const encoded = toTagged(fromTagged(toTagged(int(exact))));
defenseRatio({ attack: float(100), defense: float(20), penetration: int(0) });
counterRatio({ srcType: int(1), dstType: int(2), allCounter: false, table: RECOVERED_COUNTER_TABLE });
// @ts-expect-error Bare numbers lose Python numeric type.
calcDamage({ ...snapshot, rpgBasicActionValue: 100 });
// @ts-expect-error Structurally similar objects are not validated scalars.
toTagged({ kind: 'binary64', value: 1 });
void encoded;
rpgPropertyPercent({ property: int(101), percent: int(40), method: 0 });
// @ts-expect-error Percent must retain its Python numeric type.
rpgPropertyPercent({ property: int(101), percent: 40, method: 0 });
monsterProperty({ forced: int(0) });
monsterProperty({ forced: null, base: int(500), monsterRatio: float(1), mazeRatio: float(1), challengeRatio: int(1) });
// @ts-expect-error Override must retain its source scalar kind.
monsterProperty({ forced: 0 });
