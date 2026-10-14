import { int, float } from './numeric.js';

// Original literal fields only. common/cdata/counter_type_table.py index 8750;
// decoded SHA256 0fcde2fd8710b3e9617b1805ef4f1c74c8e155ecd21690a1f6dd622cd584874d.
// Full row/field offsets: analysis/battle-parameters/counter-types.json.
function row(beCounterID, counterID) {
  return Object.freeze({ beCounterID: int(beCounterID), beCounterRatio: float(100),
    counterID: int(counterID), counterRatio: float(120) });
}
export const RECOVERED_COUNTER_TABLE = Object.freeze({
  '1': row(4, 2), '2': row(1, 3), '3': row(2, 4), '4': row(3, 1),
  '5': row(6, 6), '6': row(5, 5), '7': Object.freeze({}),
});
