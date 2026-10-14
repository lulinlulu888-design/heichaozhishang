// ES module without Node APIs or BigInt literals. Native BigInt is mandatory;
// do not add an inexact Number fallback for unsupported client runtimes.
const owned = new WeakSet();

export function assertNumericRuntime() {
  if (typeof BigInt !== 'function') {
    throw new Error('battle-core requires native BigInt; this runtime is not supported');
  }
}

function make(kind, value) {
  const result = Object.freeze({ kind, value });
  owned.add(result);
  return result;
}

export function int(value) {
  assertNumericRuntime();
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new TypeError('int(number) requires a safe integer; use a decimal string');
  } else if (typeof value !== 'bigint' &&
      !(typeof value === 'string' && /^-?(?:0|[1-9][0-9]*)$/.test(value))) {
    throw new TypeError('int requires an exact integer, bigint or decimal string');
  }
  return make('integer', BigInt(value));
}

export function float(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError('float requires a finite binary64 number');
  }
  return make('binary64', value);
}

export function scalar(value, field = 'scalar') {
  if (!value || !owned.has(value)) throw new TypeError(`${field} requires an explicit int/float scalar`);
  return value;
}

function asFloat(value) {
  const result = Number(scalar(value).value);
  if (!Number.isFinite(result)) throw new RangeError('integer cannot be represented as finite binary64');
  return result;
}

function arithmetic(a, b, operation) {
  scalar(a); scalar(b);
  if (a.kind === 'integer' && b.kind === 'integer') return int(operation(a.value, b.value));
  return float(operation(asFloat(a), asFloat(b)));
}

export const add = (a, b) => arithmetic(a, b, (x, y) => x + y);
export const subtract = (a, b) => arithmetic(a, b, (x, y) => x - y);
export const multiply = (a, b) => arithmetic(a, b, (x, y) => x * y);

export function classicDivide(a, b) {
  scalar(a); scalar(b);
  if (b.value == 0) throw new RangeError('division by zero');
  if (a.kind === 'integer' && b.kind === 'integer') {
    let result = a.value / b.value; // JS truncates; Python 2 classic division floors.
    if (a.value % b.value != 0 && (a.value < 0) !== (b.value < 0)) result -= BigInt(1);
    return int(result);
  }
  return float(asFloat(a) / asFloat(b));
}

export function truncate(value) {
  scalar(value);
  return value.kind === 'integer' ? value : int(BigInt(Math.trunc(value.value)));
}

// JS mixed BigInt/Number comparisons are exact; converting the integer first
// would incorrectly equate 9007199254740993 and binary64 9007199254740992.
export function compare(a, b) {
  scalar(a); scalar(b);
  return a.value < b.value ? -1 : a.value > b.value ? 1 : 0;
}
export const maximum = (a, b) => compare(a, b) >= 0 ? a : b;

export function binary64Hex(value) {
  float(value);
  const bytes = new DataView(new ArrayBuffer(8));
  bytes.setFloat64(0, value, false);
  const high = bytes.getUint32(0, false), low = bytes.getUint32(4, false);
  const sign = high >>> 31 ? '-' : '';
  const exponent = (high >>> 20) & 0x7ff;
  const fraction = (high & 0xfffff).toString(16).padStart(5, '0') + low.toString(16).padStart(8, '0');
  if (exponent === 0 && (high & 0xfffff) === 0 && low === 0) return `${sign}0x0.0p+0`;
  const power = exponent === 0 ? -1022 : exponent - 1023;
  return `${sign}0x${exponent === 0 ? 0 : 1}.${fraction}p${power < 0 ? '' : '+'}${power}`;
}

export function toTagged(value) {
  scalar(value);
  if (value.kind === 'integer') return { numeric_type: 'integer', decimal: value.value.toString() };
  let decimal = Object.is(value.value, -0) ? '-0.0' : String(value.value);
  if (!/[.eE]/.test(decimal)) decimal += '.0';
  return { numeric_type: 'binary64', decimal, hex: binary64Hex(value.value) };
}

export function fromTagged(value) {
  if (!value || typeof value !== 'object') throw new TypeError('tagged scalar required');
  if (value.numeric_type === 'integer') {
    if (typeof value.decimal !== 'string') throw new TypeError('integer decimal must be a string');
    return int(value.decimal);
  }
  if (value.numeric_type !== 'binary64' || typeof value.decimal !== 'string' ||
      !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(value.decimal)) {
    throw new TypeError('invalid tagged numeric type/decimal');
  }
  const result = float(Number(value.decimal));
  if (typeof value.hex !== 'string' || binary64Hex(result.value) !== value.hex) {
    throw new TypeError('binary64 decimal/hex disagree');
  }
  return result;
}
