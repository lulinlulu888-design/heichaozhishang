export class ServiceError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'ServiceError';
    this.code = code;
    this.status = status;
  }
}

export function requireObject(value, allowed, required = []) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ServiceError('INVALID_INPUT', 'Expected a JSON object');
  }
  if (Object.keys(value).some(key => !allowed.includes(key)) || required.some(key => !(key in value))) {
    throw new ServiceError('INVALID_INPUT', 'Missing or unknown fields');
  }
}

export function displayName(value) {
  if (typeof value !== 'string' || value !== value.trim() || !value.length ||
      [...value].length > 32 || /[\u0000-\u001f\u007f]/u.test(value)) {
    throw new ServiceError('INVALID_NAME', 'Display name must contain 1–32 visible characters without outer whitespace');
  }
  return value;
}
