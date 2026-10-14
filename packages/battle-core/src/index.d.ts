declare const scalarBrand: unique symbol;
export interface IntegerScalar {
  readonly kind: 'integer'; readonly value: bigint; readonly [scalarBrand]: true;
}
export interface FloatScalar {
  readonly kind: 'binary64'; readonly value: number; readonly [scalarBrand]: true;
}
export type Scalar = IntegerScalar | FloatScalar;
export type TaggedScalar =
  | { numeric_type: 'integer'; decimal: string }
  | { numeric_type: 'binary64'; decimal: string; hex: string };
export function int(value: number | string | bigint): IntegerScalar;
export function float(value: number): FloatScalar;
export function fromTagged(value: TaggedScalar): Scalar;
export function toTagged(value: Scalar): TaggedScalar;
export function assertNumericRuntime(): void;
export function add(a: Scalar, b: Scalar): Scalar;
export function subtract(a: Scalar, b: Scalar): Scalar;
export function multiply(a: Scalar, b: Scalar): Scalar;
export function classicDivide(a: Scalar, b: Scalar): Scalar;
export function truncate(value: Scalar): IntegerScalar;
export function compare(a: Scalar, b: Scalar): -1 | 0 | 1;

/** Resolved monster base property. Force overrides bypass all other dependencies. */
export function monsterProperty(input: {
  forced: Scalar | null; base?: Scalar; monsterRatio?: Scalar; mazeRatio?: Scalar; challengeRatio?: Scalar;
}): Scalar;

/** GetRpgProps node after provider resolution. 0=floor, 1=ceil, others=unrounded. */
export function rpgPropertyPercent(input: {
  property: Scalar; percent: Scalar; method: number;
}): Scalar;

/** Optional fields are required at runtime when their original branch is active. */
export interface DamageSnapshot {
  rpgAttackType: Scalar;
  rpgBasicActionValue: Scalar; addAttackValue: Scalar;
  combatCounterRatioValue?: Scalar; dstEntityDefenseValue?: Scalar;
  attackFactorValue?: Scalar; attackedFactorValue?: Scalar;
  dstIsPlayer?: boolean; criticalRatioValue?: Scalar;
  propDamageIncValue: Scalar; propDamageReduceValue: Scalar;
  propAtkDamageIncValue?: Scalar; propAtkDamageReduceValue?: Scalar;
  propMgcDamageIncValue?: Scalar; propMgcDamageReduceValue?: Scalar;
  overwhelmRatio: Scalar; extraAttackValue: Scalar;
  /** Must be resolved using the intermediate damage after extraAttackValue. */
  extraAttackedValue: Scalar;
  extraDamage: Scalar;
  isPVP: boolean; pvpAtkRatio?: Scalar;
  /** slowHp must be resolved using the intermediate value after PVP. */
  isDamageSkillPreview: boolean; slowHp?: Scalar;
}
export interface DamageResult {
  readonly damage: IntegerScalar;
  readonly trace: ReadonlyArray<{ readonly stage: string; readonly value: Scalar }>;
}
export function calcDamage(input: DamageSnapshot): DamageResult;
export interface CardImprovement {
  factor: Scalar; property: Scalar; base: Scalar;
}
/** Explicit resolved values, not live entities or a card ID. */
export interface BlockSnapshot {
  basicBlock: Scalar;
  source: null | {
    propAddTargetShield: Scalar;
    shieldFactor: Scalar;
  };
  card: null | { extraBaseBlockPercent: Scalar; additionalBlockValue: Scalar };
  target: {
    propBeAddShield: Scalar;
    shieldFactor: Scalar;
    isPVP: boolean;
    /** Required only for PVP. */
    pvpShieldRatio?: Scalar;
  };
}
export interface BlockResult {
  readonly block: IntegerScalar;
  readonly trace: ReadonlyArray<{ readonly stage: string; readonly value: Scalar }>;
}
export function calcBlock(input: BlockSnapshot): BlockResult;
export function overwhelmRatio(input: {
  disabled: boolean; srcIsPlayer?: boolean; dstIsPlayer?: boolean; lvDiff?: Scalar;
}): Scalar;
export interface CounterRow {
  readonly beCounterID?: Scalar; readonly beCounterRatio?: Scalar;
  readonly counterID?: Scalar; readonly counterRatio?: Scalar;
}
export type CounterTable = Readonly<Record<string, CounterRow>>;
export const RECOVERED_COUNTER_TABLE: CounterTable;
export function counterRatio(input: {
  dstType: Scalar; srcType?: Scalar; allCounter: boolean; allRatio?: Scalar; table?: CounterTable;
}): Scalar;
export function defenseRatio(input: { attack: Scalar; defense?: Scalar; penetration?: Scalar }): Scalar;
export function basicActionValue(input: {
  basicDamage: Scalar;
  improvement: null | CardImprovement;
}): Scalar;
export function addAttackValue(input: {
  rpgBasicActionValue: Scalar; extraBaseDamagePercent: Scalar;
  cardAdditionalValue: Scalar; entityAttackAddValue: Scalar;
}): Scalar;
export function attackFactorValue(input: {
  factors: readonly Scalar[]; commonFactors: readonly Scalar[]; cardFactor: Scalar; battleFactor: Scalar;
}): Scalar;
export function attackedFactorValue(input: {
  factors: readonly Scalar[]; commonFactors: readonly Scalar[]; excluded: boolean; reduceDamagedRate?: Scalar;
}): Scalar;
export function propertyValue(input: {
  base: Scalar; modifiers: readonly Scalar[]; isPropAtk: boolean;
}): Scalar;
export function criticalOutcome(input: {
  srcCritical: Scalar; defendCritical: Scalar; blockProperty: Scalar; draw: Scalar;
  srcCriticalDamage?: Scalar; cardExtra?: Scalar; blockDamageProperty?: Scalar;
}): Readonly<{ kind: IntegerScalar; ratio: Scalar }>;
