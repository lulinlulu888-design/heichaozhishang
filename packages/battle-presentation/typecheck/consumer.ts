import {
  createProjection, receiveBatch, playNext, inspectProjection, integerValue,
  type Snapshot, type Batch, type PlaybackEvent,
} from '../src/index.js';
const initial: Snapshot = {
  snapshotId: 'initial',
  entities: [{ id: 'elsa', hp: integerValue('9007199254740993'), shield: integerValue('0') }],
  teams: [],
};
const batch: Batch = {
  batchId: 'synthetic-1',
  actions: [{ type: 'Group', kind: 'Target', id: 'target-1', actions: [
    { type: 'HpChange', targetId: 'elsa', deltaValue: integerValue('-1'), finalValue: integerValue('9007199254740992') },
  ] }],
};
const received = receiveBatch(createProjection(initial), batch);
const played = playNext(received.projection, inspectProjection(received.projection).pendingCount);
function describe(event: PlaybackEvent): string {
  switch (event.type) {
    case 'GroupBegin': case 'GroupEnd': return event.group.id;
    case 'SnapshotApplied': return event.snapshot.snapshotId;
    case 'HpChange': case 'ShieldChange': return event.finalValue.decimal;
  }
}
played.events.map(describe);
