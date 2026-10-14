declare const projectionBrand: unique symbol;
/** Immutable, opaque in-memory value. Not a serializable session or authority. */
export interface Projection { readonly [projectionBrand]: true }
export type TaggedValue =
  | Readonly<{ numeric_type: 'integer'; decimal: string }>
  | Readonly<{ numeric_type: 'binary64'; decimal: string; hex: string }>;
export type PileName = 'handPile' | 'drawPile' | 'discardPile' | 'exhaustedPile' | 'powerUsedPile';
export interface Entity {
  readonly id: string;
  readonly hp: TaggedValue;
  readonly shield: TaggedValue;
}
export interface Card {
  readonly id: string;
  readonly cardTypeId: string;
  readonly charId: string;
}
export interface Team {
  readonly id: string;
  readonly cards: readonly Card[];
  readonly piles: Readonly<Record<PileName, readonly string[]>>;
}
/** Complete replacement of this module's selected fields, never a partial patch. */
export interface Snapshot {
  readonly snapshotId: string;
  readonly entities: readonly Entity[];
  readonly teams: readonly Team[];
}
export type GroupKind = 'SkillUse' | 'SkillEachState' | 'Target';
export interface ChangeAction {
  readonly type: 'HpChange' | 'ShieldChange';
  readonly targetId: string;
  readonly deltaValue: TaggedValue;
  readonly finalValue: TaggedValue;
}
export interface SnapshotAction {
  readonly type: 'SyncSnapshot';
  readonly snapshot: Snapshot;
}
export interface GroupAction {
  readonly type: 'Group';
  readonly kind: GroupKind;
  readonly id: string;
  readonly actions: readonly Action[];
}
export type Action = ChangeAction | SnapshotAction | GroupAction;
export interface Batch { readonly batchId: string; readonly actions: readonly Action[] }
export interface Location { readonly batchId: string; readonly actionPath: readonly number[] }
export interface GroupRef extends Location { readonly id: string; readonly kind: GroupKind }
export interface SnapshotReceipt extends Location {
  readonly type: 'SnapshotReceived';
  readonly previousSnapshotId: string;
  readonly snapshotId: string;
}
export interface EventLocation extends Location { readonly sequence: number }
export interface GroupEvent extends EventLocation {
  readonly type: 'GroupBegin' | 'GroupEnd';
  readonly group: GroupRef;
  /** One-based nesting depth; GroupEnd reports depth before exiting. */
  readonly depth: number;
}
export interface ChangeEvent extends EventLocation {
  readonly type: 'HpChange' | 'ShieldChange';
  readonly targetId: string;
  readonly previousValue: TaggedValue;
  readonly deltaValue: TaggedValue;
  readonly finalValue: TaggedValue;
}
export interface SnapshotEvent extends EventLocation {
  readonly type: 'SnapshotApplied';
  readonly snapshot: Snapshot;
}
export type PlaybackEvent = GroupEvent | ChangeEvent | SnapshotEvent;
export interface ProjectionView {
  /** Last accepted explicit SyncSnapshot; change actions do not calculate this. */
  readonly receivedSnapshot: Snapshot;
  /** Playback position: may have finalValue assignments after the named snapshot. */
  readonly visibleState: Snapshot;
  readonly pendingCount: number;
  readonly playedCount: number;
  readonly receivedBatchCount: number;
  readonly activeGroups: readonly GroupRef[];
}
export const LIMITS: Readonly<{
  entities: number; teams: number; cards: number; batchActions: number;
  groupDepth: number; pendingEvents: number; batches: number; integerDigits: number;
}>;
export const PILE_NAMES: readonly PileName[];
/** Canonical integer decimal string; never converted through Number or BigInt. */
export function integerValue(decimal: string): TaggedValue;
export function binary64Value(value: number): TaggedValue;
export function createProjection(initialSnapshot: Snapshot): Projection;
/** Pure and atomic. Caller commits by retaining the returned projection. */
export function receiveBatch(projection: Projection, batch: Batch): Readonly<{
  projection: Projection; receipts: readonly SnapshotReceipt[];
}>;
/** Count includes group boundaries and snapshots. At least one pending event. */
export function playNext(projection: Projection, count?: number): Readonly<{
  projection: Projection; events: readonly PlaybackEvent[];
}>;
export function inspectProjection(projection: Projection): ProjectionView;
