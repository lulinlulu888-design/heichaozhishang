/** Static Python RpcChannel reference format, not a verified AsioGateClient codec. */
export const MAX_BODY_LENGTH = 0xffffff;

/** Header length includes uint16 method ordinal and protobuf, excludes uint32 length. */
export function encodeFrame(methodIndex, payload) {
  // The recovered CallMethod asserts index < 65535 before struct.pack('<H', ...).
  if (!Number.isInteger(methodIndex) || methodIndex < 0 || methodIndex >= 65535) {
    throw new RangeError('methodIndex must be an integer from 0 through 65534');
  }
  if (!(payload instanceof Uint8Array)) throw new TypeError('payload must be Buffer or Uint8Array');
  const bodyLength = payload.byteLength + 2;
  if (bodyLength > MAX_BODY_LENGTH) throw new RangeError('frame body exceeds 0xffffff bytes');
  const frame = Buffer.allocUnsafe(bodyLength + 4);
  frame.writeUInt32LE(bodyLength, 0);
  frame.writeUInt16LE(methodIndex, 4);
  frame.set(payload, 6);
  return frame;
}

/**
 * Incremental reference frame decoder. push() returns complete {methodIndex,payload}
 * frames; finish() rejects a truncated final frame. Invalid input poisons the
 * decoder: create a new instance for a new stream rather than resynchronizing.
 * Method ordinals are raw uint16 values; this layer does not dispatch or validate RPCs.
 */
export class FrameDecoder {
  #header = Buffer.alloc(4);
  #headerBytes = 0;
  #body = null;
  #bodyBytes = 0;
  #maxBodyLength;
  #failed = false;
  #finished = false;

  constructor({ maxBodyLength = MAX_BODY_LENGTH } = {}) {
    if (!Number.isInteger(maxBodyLength) || maxBodyLength < 2 || maxBodyLength > MAX_BODY_LENGTH) {
      throw new RangeError('maxBodyLength must be between 2 and 0xffffff');
    }
    this.#maxBodyLength = maxBodyLength;
  }

  #checkOpen() {
    if (this.#failed) throw new Error('frame decoder is in a failed state');
    if (this.#finished) throw new Error('frame decoder is finished');
  }

  push(chunk) {
    this.#checkOpen();
    if (!(chunk instanceof Uint8Array)) throw new TypeError('chunk must be Buffer or Uint8Array');
    const input = Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    const frames = [];
    let position = 0;
    try {
      while (position < input.length) {
        if (!this.#body) {
          const count = Math.min(4 - this.#headerBytes, input.length - position);
          input.copy(this.#header, this.#headerBytes, position, position + count);
          position += count;
          this.#headerBytes += count;
          if (this.#headerBytes < 4) break;
          const bodyLength = this.#header.readUInt32LE(0);
          if (bodyLength < 2 || bodyLength > this.#maxBodyLength) {
            throw new RangeError(`invalid frame body length: ${bodyLength}`);
          }
          this.#body = Buffer.allocUnsafe(bodyLength);
          this.#bodyBytes = 0;
        }
        const count = Math.min(this.#body.length - this.#bodyBytes, input.length - position);
        input.copy(this.#body, this.#bodyBytes, position, position + count);
        position += count;
        this.#bodyBytes += count;
        if (this.#bodyBytes === this.#body.length) {
          frames.push({ methodIndex: this.#body.readUInt16LE(0), payload: this.#body.subarray(2) });
          this.#body = null;
          this.#bodyBytes = 0;
          this.#headerBytes = 0;
        }
      }
    } catch (error) {
      this.#failed = true;
      this.#body = null;
      throw error;
    }
    return frames;
  }

  finish() {
    this.#checkOpen();
    if (this.#headerBytes || this.#body) {
      this.#failed = true;
      this.#body = null;
      throw new Error('truncated frame at end of stream');
    }
    this.#finished = true;
  }
}
