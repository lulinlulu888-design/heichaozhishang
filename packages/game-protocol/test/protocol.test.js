import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { loadProtocol } from '../src/index.js';

const protocol = await loadProtocol();
const bytes = hex => Buffer.from(hex, 'hex');

// Hand-derived from field numbers/types in the native embedded descriptors.
// These are static schema vectors, NOT packets captured from a running APK.
const vectors = [
  ['Void', {}, ''],
  ['ConnectServerRequest', { type: 0 }, '1000'],
  ['ConnectServerReply', { type: 1 }, '1001'],
  ['Md5OrIndex', { index: -1 }, '1001'],
  ['SessionSeed', { seed: '1' }, '0801'],
  ['SessionSeed', { seed: '9007199254740993' }, '088180808080808010'],
  ['SessionSeed', { seed: '9223372036854775807' }, '08ffffffffffffffff7f'],
  ['SessionSeed', { seed: '-9223372036854775808' }, '0880808080808080808001'],
  ['EncryptString', { encryptstr: bytes('00ff80') }, '0a0300ff80'],
  ['SessionKey', { random_padding_header: bytes('00'), session_key: bytes('ff80'), seed: '1', random_padding_tail: bytes('fe') }, '0a01001202ff8018012201fe'],
  ['EntityMessage', { method: { index: -1 }, parameters: bytes('00ff'), reliable: false }, '1a021001220200ff2800'],
  ['ServiceMessage', { entity_msg: { method: { index: 1 } } }, '0a041a021002'],
  ['FilterRule', { idlist: [bytes('00'), bytes('ff')] }, '1a01001a01ff'],
];

for (const [name, value, hex] of vectors) {
  test(`static descriptor vector: ${name} ${hex || '(empty)'}`, () => {
    assert.equal(protocol.encode(name, value).toString('hex'), hex);
    assert.deepEqual(protocol.decode(name, bytes(hex)), value);
  });
}

test('required fields are checked before encoding, even with proto2 defaults', () => {
  for (const [name, value] of [['SessionSeed', {}], ['SessionKey', { seed: '1' }],
    ['ConnectServerReply', {}], ['EntityMessage', {}], ['ServiceMessage', { entity_msg: {} }]]) {
    assert.throws(() => protocol.encode(name, value), /required field missing/);
  }
  assert.equal(protocol.encode('EncryptString', { encryptstr: Buffer.alloc(0) }).toString('hex'), '0a00');
});

test('decoding rejects missing required fields and truncated bytes', () => {
  for (const name of ['SessionSeed', 'SessionKey', 'ConnectServerReply', 'EntityMessage']) {
    assert.throws(() => protocol.decode(name, Buffer.alloc(0)), /missing required/);
  }
  assert.throws(() => protocol.decode('EncryptString', bytes('0a0300')));
  assert.throws(() => protocol.decode('SessionSeed', bytes('0880')));
});

test('int64 accepts exact representations and rejects lossy or overflowing inputs', () => {
  assert.equal(protocol.encode('SessionSeed', { seed: 9007199254740993n }).toString('hex'), '088180808080808010');
  assert.equal(protocol.encode('SessionSeed', { seed: 1 }).toString('hex'), '0801');
  for (const seed of [9007199254740992, 1.5, '9223372036854775808', '-9223372036854775809', '1.0', '1e2', true]) {
    assert.throws(() => protocol.encode('SessionSeed', { seed }));
  }
});

test('field names and scalar types do not silently change during conversion', () => {
  assert.throws(() => protocol.encode('SessionKey', { sessionKey: bytes('ff') }), /unknown field/);
  assert.throws(() => protocol.encode('EncryptString', { encryptstr: 'base64' }), /Buffer or Uint8Array/);
  assert.throws(() => protocol.encode('ConnectServerRequest', { type: 99 }));
  assert.throws(() => protocol.encode('Md5OrIndex', { index: 4294967295 }), /range/);
  assert.throws(() => protocol.encode('Md5OrIndex', { index: 1.1 }), /range/);
  assert.throws(() => protocol.encode('EntityMessage', { method: {}, reliable: 'false' }));
  assert.throws(() => protocol.encode('Void', null));
  assert.throws(() => protocol.decode('Void', []));
});

test('omitted optional fields stay omitted, explicit default values remain present', () => {
  assert.deepEqual(protocol.decode('EntityMessage', bytes('1a00')), { method: {} });
  assert.deepEqual(protocol.decode('EntityMessage', bytes('1a002801')), { method: {}, reliable: true });
  assert.equal(protocol.encode('mobile.server.SessionSeed', { seed: '1' }).toString('hex'), '0801');
  assert.throws(() => protocol.encode('NoSuchMessage', {}));
});

test('checked-in schema text matches its extraction provenance', async () => {
  const provenance = JSON.parse(await readFile(new URL('../schemas/provenance.json', import.meta.url), 'utf8'));
  for (const record of provenance.schemas) {
    const content = await readFile(new URL(`../schemas/${record.name}`, import.meta.url));
    assert.equal(createHash('sha256').update(content).digest('hex'), record.schema_text_sha256);
  }
});
