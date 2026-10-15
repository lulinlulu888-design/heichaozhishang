import type { TaggedScalar } from '../../battle-core/src/index.js';
export type Health = Readonly<TaggedScalar>;
export type Side = 'player' | 'enemy';
export type Status = 'player-turn' | 'won' | 'lost';
export type OutcomeReason = 'enemy-defeated' | 'player-defeated' | 'round-limit';
export type PileZone = 'hand' | 'draw' | 'discard' | 'exhausted' | 'powerUsed' | 'removed';
export type Effect =
  | Readonly<{ type: 'damage' | 'shield'; target: 'self' | 'opponent'; amount: string }>
  | Readonly<{ type: 'heal'; target: 'self' | 'opponent'; amount: string }>
  | Readonly<{ type: 'breakdown'; target: 'opponent'; stacks: number }>
  | Readonly<{ type: 'draw'; count: number }>;
export type EnemyEffect = Exclude<Effect, { type: 'draw' }>;
export interface CardInstance { readonly instanceId: string; readonly cardId: string }
export interface CombatantDefinition { readonly id: string; readonly name: string; readonly maxHp: Health }
export interface UltimateRules {
  readonly policy: 'elsa-combo-reconstruction-v1'; readonly ownerId: '1'; readonly cardId: '410104';
  readonly pointsRequired: 3; readonly maxPerRound: 3;
}
export interface CardDefinition {
  readonly name: string; readonly cost: number; readonly effects: readonly Effect[];
  /** All four fields are required only with ultimateRules; legacy definitions reject them. */
  readonly ownerId?: string; readonly cardType?: 0 | 1 | 2 | 3 | 6 | 7;
  readonly specialPoints?: 0 | 1; readonly removeOnLeaveHand?: boolean;
}
export interface BattleDefinition {
  /** Opt-in v2 reconstruction; healing/breakdown require this explicit policy. */
  readonly statusRules?: Readonly<{ policy: 'breakdown-reconstruction-v1'; attack: Readonly<Record<Side, Health>> }>;
  /** Explicit v3 single-owner reconstruction. Never inferred for old saved definitions. */
  readonly ultimateRules?: UltimateRules;
  readonly id: string;
  readonly player: CombatantDefinition;
  readonly enemy: CombatantDefinition;
  /** Explicit order; createBattle draws from the start without shuffling. */
  readonly deck: readonly CardInstance[];
  readonly cards: Readonly<Record<string, CardDefinition>>;
  readonly enemySkills: Readonly<Record<string, Readonly<{ effects: readonly EnemyEffect[] }>>>;
  /** Index 0 is round 1; every list is an ordered, nonempty skill sequence. */
  readonly enemyIntents: readonly (readonly string[])[];
  readonly enemyFallback: readonly string[];
  readonly initialDraw: number;
  readonly roundDraw: number;
  readonly energyPerRound: number;
  readonly handLimit: number;
  readonly maxRounds: number;
}
export interface EntityState { readonly hp: Health; readonly shield: Health }
export interface BattleState {
  readonly format: 'hczs-battle-session-v1' | 'hczs-battle-session-v2' | 'hczs-battle-session-v3';
  /** Required exactly when statusRules is present. */
  readonly breakdown?: Readonly<Record<Side, number>>;
  /** Required exactly when ultimateRules is present. */
  readonly ultimate?: Readonly<{ chainOwnerId: string | null; points: number; generatedThisRound: number; generatedTotal: number }>;
  readonly definitionId: string;
  readonly round: number;
  readonly status: Status;
  readonly outcomeReason: OutcomeReason | null;
  readonly energy: number;
  readonly player: EntityState;
  readonly enemy: EntityState;
  /** Exact definition.deck prefix; v3 appends deterministic ultimate:N instances. */
  readonly cards: readonly CardInstance[];
  readonly piles: Readonly<Record<PileZone, readonly string[]>>;
  readonly rng: Readonly<{ algorithm: 'mulberry32-v1'; state: number }>;
  readonly actionIndex: number;
}
interface HealthChange {
  readonly previousHp: Health; readonly finalHp: Health;
  readonly previousShield: Health; readonly finalShield: Health;
}
export type BattleEvent =
  | Readonly<{ type: 'BreakdownChanged'; actor: Side; target: Side; previousStacks: number; finalStacks: number; reason: 'applied' | 'healed' }>
  | Readonly<{ type: 'BreakdownTriggered'; actor: Side; target: Side; stacks: number; amount: string }>
  | Readonly<{ type: 'HealthRestored'; actor: Side; target: Side; effectIndex: number; amount: string; restored: Health } & HealthChange>
  | Readonly<{ type: 'BattleStarted'; definitionId: string; seed: number }>
  | Readonly<{ type: 'TurnStarted'; round: number }>
  | Readonly<{ type: 'CardPlayed'; instanceId: string; cardId: string; cost: number }>
  | Readonly<{ type: 'CardMoved'; instanceId: string; from: 'hand' | 'in-flight'; to: 'discard' | 'removed' }>
  | Readonly<{ type: 'CardDrawn'; instanceId: string; generated?: true }>
  | Readonly<{ type: 'DiscardRecycled'; order: readonly string[]; rngBefore: number; rngAfter: number }>
  | Readonly<{ type: 'EnergyChanged'; previousValue: number; finalValue: number }>
  | Readonly<{ type: 'DamageApplied'; actor: Side; target: Side; effectIndex: number; amount: string; absorbed: Health; hpLost: Health } & HealthChange>
  | Readonly<{ type: 'ShieldAdded'; actor: Side; target: Side; effectIndex: number; amount: string } & HealthChange>
  | Readonly<{ type: 'ShieldCleared'; target: Side } & HealthChange>
  | Readonly<{ type: 'EnemySkillUsed'; skillId: string; round: number }>
  | Readonly<{ type: 'BattleEnded'; status: 'won' | 'lost'; reason: OutcomeReason; round: number }>
  | Readonly<{ type: 'StateUpdated'; state: BattleState }>;
export interface BattleResult { readonly state: BattleState; readonly events: readonly BattleEvent[] }
export const FORMAT: 'hczs-battle-session-v1';
export const STATUS_FORMAT: 'hczs-battle-session-v2';
export const ULTIMATE_FORMAT: 'hczs-battle-session-v3';
export const LIMITS: Readonly<{ cards: number; cardDefinitions: number; enemySkills: number; effects: number;
  skillsPerTurn: number; rounds: number; energy: number; actions: number; amountDigits: number; healthDigits: number }>;
export function validateDefinition(definition: BattleDefinition): BattleDefinition;
/** Structural validation and immutable copy, not proof of an authentic play history. */
export function validateState(definition: BattleDefinition, state: BattleState): BattleState;
export function createBattle(definition: BattleDefinition, seed: number): BattleResult;
export function playCard(definition: BattleDefinition, state: BattleState, instanceId: string): BattleResult;
export function endTurn(definition: BattleDefinition, state: BattleState): BattleResult;
