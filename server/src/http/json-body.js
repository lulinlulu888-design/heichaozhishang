import { ServiceError } from '../errors.js';
const MAX_BODY = 16 * 1024;

export function jsonBody(request) {
  // A profile lookup can finish after the client has already disconnected.
  // Those stream events will not be replayed for listeners added below.
  if (request.aborted || (request.destroyed && !request.complete)) {
    return Promise.reject(new ServiceError('REQUEST_ABORTED', 'Request aborted'));
  }
  if (request.headers['content-type']?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    request.resume();
    return Promise.reject(new ServiceError('JSON_REQUIRED', 'Use application/json', 415));
  }
  return new Promise((resolve, reject) => {
    let size = 0;
    let failed = false;
    const parts = [];
    request.on('data', chunk => {
      if (failed) return;
      size += chunk.length;
      if (size > MAX_BODY) {
        failed = true;
        parts.length = 0;
        reject(new ServiceError('BODY_TOO_LARGE', 'Request body exceeds 16 KiB', 413));
      } else parts.push(chunk);
    });
    request.on('end', () => {
      if (failed) return;
      try { resolve(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(parts)))); }
      catch { reject(new ServiceError('INVALID_JSON', 'Request is not valid UTF-8 JSON')); }
    });
    request.on('error', reject);
    request.on('aborted', () => reject(new ServiceError('REQUEST_ABORTED', 'Request aborted')));
  });
}
