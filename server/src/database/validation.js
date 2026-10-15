import { ServiceError } from '../errors.js';
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const REQUEST = /^[A-Za-z0-9._:-]{1,128}$/;
export const integer = (value, min = 0) => Number.isSafeInteger(value) && value >= min;
export function requireProfileId(id) { if (typeof id !== 'string' || !UUID.test(id)) throw new ServiceError('INVALID_INPUT', 'A canonical local profile UUID is required'); }
export function stored(condition) { if (!condition) throw new ServiceError('SAVE_CORRUPT', 'Stored reconstruction data failed validation', 500); }
export function exactKeys(value, keys) { return value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value, k)); }
export const options = { strict: 'throw', versionKey: false, autoIndex: false, autoCreate: false };
export function numberField(min = 0) { return { type: Number, required: true, validate: value => integer(value, min) }; }
export async function initModels(models) { for (const model of models) { await model.createCollection(); await model.createIndexes(); } }
