import { fileURLToPath } from 'node:url';
import protobuf from 'protobufjs';

export { encodeFrame, FrameDecoder, MAX_BODY_LENGTH } from './reference-frame.js';

const schemaPath = fileURLToPath(new URL('../schemas/client_gate.proto', import.meta.url));
const longTypes = new Set(['int64', 'sint64', 'sfixed64', 'uint64', 'fixed64']);
const integerTypes = new Set(['int32', 'sint32', 'sfixed32', 'uint32', 'fixed32']);

function normalizeLong(value, field, path) {
  if (typeof value === 'number' && !Number.isSafeInteger(value)) {
    throw new TypeError(`${path}: use a decimal string or bigint for an unsafe integer`);
  }
  if (!['number', 'string', 'bigint'].includes(typeof value) || !/^-?(0|[1-9]\d*)$/.test(String(value))) {
    throw new TypeError(`${path}: expected an integer, bigint or decimal string`);
  }
  const number = BigInt(value);
  const unsigned = field.type === 'uint64' || field.type === 'fixed64';
  const min = unsigned ? 0n : -(1n << 63n);
  const max = unsigned ? (1n << 64n) - 1n : (1n << 63n) - 1n;
  if (number < min || number > max) throw new RangeError(`${path}: outside ${field.type} range`);
  return protobuf.util.Long.fromString(number.toString(), unsigned);
}

function normalizeField(field, value, path) {
  if (field.resolvedType instanceof protobuf.Type) return normalizeMessage(field.resolvedType, value, path);
  if (longTypes.has(field.type)) return normalizeLong(value, field, path);
  if (field.type === 'bytes' && !(value instanceof Uint8Array)) {
    throw new TypeError(`${path}: expected Buffer or Uint8Array`);
  }
  if (integerTypes.has(field.type)) {
    const unsigned = field.type === 'uint32' || field.type === 'fixed32';
    if (!Number.isInteger(value) || value < (unsigned ? 0 : -2147483648) || value > (unsigned ? 4294967295 : 2147483647)) {
      throw new RangeError(`${path}: outside ${field.type} range`);
    }
  }
  return value;
}

function normalizeMessage(type, value, path = type.fullName) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value instanceof Uint8Array) {
    throw new TypeError(`${path}: expected a field object`);
  }
  for (const key of Object.keys(value)) {
    if (!Object.hasOwn(type.fields, key)) throw new TypeError(`${path}.${key}: unknown field (names use snake_case)`);
  }
  const result = {};
  for (const field of type.fieldsArray) {
    const present = Object.hasOwn(value, field.name);
    if (!present) {
      if (field.required) throw new TypeError(`${path}.${field.name}: required field missing`);
      continue;
    }
    const item = value[field.name];
    if (item == null) throw new TypeError(`${path}.${field.name}: null or undefined is not a field value`);
    if (field.repeated) {
      if (!Array.isArray(item)) throw new TypeError(`${path}.${field.name}: expected an array`);
      result[field.name] = item.map((entry, index) => normalizeField(field, entry, `${path}.${field.name}[${index}]`));
    } else {
      result[field.name] = normalizeField(field, item, `${path}.${field.name}`);
    }
  }
  return result;
}

/**
 * Load statically recovered protobuf schemas; no sockets, RPC or game logic.
 * int64 input: decimal string, bigint, or safe integer. Decoded int64: string.
 * bytes input/output: Uint8Array/Buffer. Field names retain original snake_case.
 */
export async function loadProtocol() {
  const root = new protobuf.Root();
  await root.load(schemaPath, { keepCase: true });
  root.resolveAll();

  function lookup(name) {
    if (typeof name !== 'string' || !name) throw new TypeError('message type name is required');
    return root.lookupType(name.includes('.') ? name : `mobile.server.${name}`);
  }

  return Object.freeze({
    encode(name, fields) {
      const type = lookup(name);
      const value = normalizeMessage(type, fields);
      const error = type.verify(value);
      if (error) throw new TypeError(`${type.fullName}: ${error}`);
      return Buffer.from(type.encode(value).finish());
    },
    decode(name, bytes) {
      if (!(bytes instanceof Uint8Array)) throw new TypeError('payload must be Buffer or Uint8Array');
      const type = lookup(name);
      const message = type.decode(bytes);
      return type.toObject(message, { longs: String, bytes: Buffer, defaults: false });
    },
  });
}
