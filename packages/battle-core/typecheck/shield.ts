import { int, float, calcBlock } from '../src/index.js';
import type { BlockSnapshot } from '../src/index.js';
const input: BlockSnapshot = {
  basicBlock: int(300), source: null, card: null,
  target: { propBeAddShield: int(0), shieldFactor: float(0), isPVP: false },
};
const block: bigint = calcBlock(input).block.value;
// @ts-expect-error The original function requires a real target for battleInst.
calcBlock({ ...input, target: null });
// @ts-expect-error Numeric values carry explicit Python numeric types.
calcBlock({ ...input, basicBlock: 300 });
// @ts-expect-error Missing card is not the same as explicit absence.
calcBlock({ basicBlock: int(1), target: input.target, source: null });
void block;
