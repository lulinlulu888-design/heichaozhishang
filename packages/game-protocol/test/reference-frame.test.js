import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeFrame, FrameDecoder, MAX_BODY_LENGTH } from '../src/index.js';

// Derived from Python pack('<I', len(proto)+2) + pack('<H', index) + proto.
// Not captured from AsioGateClient or a running game.
const vector = Buffer.from('0400000001000801', 'hex');
const expected = { methodIndex: 1, payload: Buffer.from('0801', 'hex') };

test('reference frame golden bytes use little-endian length and ordinal', () => {
  assert.equal(encodeFrame(1, expected.payload).toString('hex'), vector.toString('hex'));
  assert.equal(encodeFrame(0x1234, Buffer.alloc(0)).toString('hex'), '020000003412');
  const decoder = new FrameDecoder();
  assert.deepEqual(decoder.push(vector), [expected]);
  decoder.finish();
});

test('every possible single split of the golden frame decodes correctly', () => {
  for (let cut = 0; cut <= vector.length; cut++) {
    const decoder = new FrameDecoder();
    const frames = [...decoder.push(vector.subarray(0, cut)), ...decoder.push(vector.subarray(cut))];
    assert.deepEqual(frames, [expected], `split ${cut}`);
    decoder.finish();
  }
});

test('one-byte fragments and coalesced frames preserve their order', () => {
  const second = encodeFrame(2, Buffer.alloc(0));
  const stream = Buffer.concat([vector, second, vector]);
  const wanted = [expected, { methodIndex: 2, payload: Buffer.alloc(0) }, expected];
  const fragmented = new FrameDecoder();
  const result = [...stream].flatMap(byte => fragmented.push(Uint8Array.of(byte)));
  assert.deepEqual(result, wanted);
  fragmented.finish();
  const coalesced = new FrameDecoder();
  assert.deepEqual(coalesced.push(stream), wanted);
  coalesced.finish();
});

test('length below two and above the limit fail immediately on the header', () => {
  for (const size of [0, 1, MAX_BODY_LENGTH + 1, 0xffffffff]) {
    const header = Buffer.alloc(4);
    header.writeUInt32LE(size);
    const decoder = new FrameDecoder();
    assert.throws(() => decoder.push(header), /invalid frame body length/);
    assert.throws(() => decoder.push(vector), /failed state/);
  }
  const restricted = new FrameDecoder({ maxBodyLength: 3 });
  assert.throws(() => restricted.push(vector.subarray(0, 4)), /invalid frame body length/);
});

test('truncated headers and bodies cannot complete a stream', () => {
  for (let cut = 1; cut < vector.length; cut++) {
    const decoder = new FrameDecoder();
    assert.deepEqual(decoder.push(vector.subarray(0, cut)), []);
    assert.throws(() => decoder.finish(), /truncated frame/);
  }
  const empty = new FrameDecoder();
  empty.finish();
  assert.throws(() => empty.push(vector), /finished/);
});

test('sender index and frame allocation limits are explicit', () => {
  for (const index of [-1, 1.5, 65535, 65536]) assert.throws(() => encodeFrame(index, Buffer.alloc(0)), /methodIndex/);
  assert.equal(encodeFrame(65534, Buffer.alloc(0)).toString('hex'), '02000000feff');
  assert.throws(() => encodeFrame(0, new Uint8Array(MAX_BODY_LENGTH - 1)), /exceeds/);
  for (const maxBodyLength of [1, MAX_BODY_LENGTH + 1, NaN]) assert.throws(() => new FrameDecoder({ maxBodyLength }), /maxBodyLength/);
});

test('decoder returns a raw uint16 without pretending to know RPC dispatch', () => {
  const decoder = new FrameDecoder();
  assert.deepEqual(decoder.push(Buffer.from('02000000ffff', 'hex')), [{ methodIndex: 65535, payload: Buffer.alloc(0) }]);
  decoder.finish();
});
