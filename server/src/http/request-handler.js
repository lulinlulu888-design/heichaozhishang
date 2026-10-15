import Koa from 'koa';
import { ServiceError } from '../errors.js';
import { jsonBody } from './json-body.js';

// Koa owns response completion; domain code receives no Koa context.
export function createRequestHandler({ allowedOrigins, getPort, isClosing, dispatch, log }) {
  const origins = new Set(allowedOrigins);
  const app = new Koa();
  app.proxy = false;
  app.on('error', error => log({ event: 'request-failed', error: error.name ?? 'Error' }));
  app.use(async ctx => {
    const request = ctx.req;
    const send = (status, value) => {
      ctx.status = status;
      ctx.set('Content-Type', 'application/json; charset=utf-8');
      ctx.set('Cache-Control', 'no-store');
      ctx.set('X-Content-Type-Options', 'nosniff');
      ctx.body = JSON.stringify(value);
    };
    try {
      if (isClosing()) {
        ctx.set('Connection', 'close');
        throw new ServiceError('SHUTTING_DOWN', 'The local service is stopping', 503);
      }
      const actualPort = getPort();
      if (![`127.0.0.1:${actualPort}`, `localhost:${actualPort}`].includes(request.headers.host)) {
        throw new ServiceError('HOST_NOT_ALLOWED', 'Use the loopback service address', 403);
      }
      const origin = request.headers.origin;
      if (origin !== undefined) {
        if (!origins.has(origin)) throw new ServiceError('ORIGIN_NOT_ALLOWED', 'Origin is not configured', 403);
        ctx.set('Access-Control-Allow-Origin', origin);
        ctx.set('Vary', 'Origin');
      }
      if (request.method === 'OPTIONS') {
        ctx.status = 204;
        ctx.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS');
        ctx.set('Access-Control-Allow-Headers', 'Content-Type');
        return;
      }
      const url = new URL(request.url, 'http://127.0.0.1');
      if (url.search) throw new ServiceError('INVALID_INPUT', 'Query parameters are not supported');
      await dispatch({ request, path: url.pathname, readBody: () => jsonBody(request), send });
    } catch (error) {
      if (ctx.res.destroyed) return;
      if (error instanceof ServiceError) send(error.status, { error: { code: error.code, message: error.message } });
      else {
        log({ event: 'request-failed', error: error.name ?? 'Error' });
        send(500, { error: { code: 'INTERNAL_ERROR', message: 'The operation could not be completed' } });
      }
    }
  });
  return app.callback();
}
