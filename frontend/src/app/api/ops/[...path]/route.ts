import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const routes: Record<string, RegExp[]> = {
  GET: [/^(health\/ready|meta|overview|incidents|runs|approvals|evaluations|architecture)$/,
    /^(incidents|runs)\/[0-9a-f-]{36}$/],
  POST: [/^(session|simulation|runs)$/, /^runs\/[0-9a-f-]{36}\/resume$/,
    /^approvals\/[0-9a-f-]{36}\/decision$/],
  DELETE: [/^session$/],
};

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const route = path.join('/');
  if (!routes[request.method]?.some(pattern => pattern.test(route)) || request.nextUrl.search) {
    return NextResponse.json({ detail: 'ROUTE_NOT_ALLOWED' }, { status: 404 });
  }
  const backend = process.env.OPSPILOT_DASHBOARD_BACKEND_URL;
  const key = process.env.OPSPILOT_DASHBOARD_SERVICE_KEY;
  if (!backend || !key) {
    return NextResponse.json({ detail: 'DASHBOARD_NOT_CONFIGURED' }, { status: 503 });
  }
  const url = new URL(backend);
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)
    || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    return NextResponse.json({ detail: 'BACKEND_CONFIGURATION_INVALID' }, { status: 503 });
  }
  const headers: Record<string, string> = { 'X-Dashboard-Key': key };
  // Never forward arbitrary authorization headers or browser-selected backend credentials.
  const cookie = request.cookies.get('opspilot_session');
  if (cookie && /^[0-9a-f]{64}$/.test(cookie.value)) {
    headers.Cookie = `opspilot_session=${cookie.value}`;
  }
  let body: string | undefined;
  if (request.method !== 'GET') {
    // NextURL can normalize 127.0.0.1 to localhost. Compare with the actual, bounded
    // loopback Host header, then pass that exact origin to the independent backend.
    const host = request.headers.get('host') || '';
    const origin = `${request.nextUrl.protocol}//${host}`;
    if (!/^(127\.0\.0\.1|localhost):\d{2,5}$/.test(host)
      || request.headers.get('origin') !== origin) {
      return NextResponse.json({ detail: 'ORIGIN_REJECTED' }, { status: 403 });
    }
    if (request.headers.get('content-type')?.split(';')[0] !== 'application/json') {
      return NextResponse.json({ detail: 'JSON_REQUIRED' }, { status: 415 });
    }
    const reader = request.body?.getReader();
    let length = 0;
    const chunks: Uint8Array[] = [];
    if (reader) {
      const deadline = AbortSignal.timeout(5000);
      let rejectDeadline: () => void = () => {};
      const expired = new Promise<never>((_, reject) => {
        rejectDeadline = () => reject(new Error('BODY_TIMEOUT'));
        deadline.addEventListener('abort', rejectDeadline, { once: true });
      });
      try {
        while (true) {
          const part = await Promise.race([reader.read(), expired]);
          if (part.done) break;
          length += part.value.byteLength;
          if (length > 16384) {
            void reader.cancel().catch(() => {});
            return NextResponse.json({ detail: 'BODY_TOO_LARGE' }, { status: 413 });
          }
          chunks.push(part.value);
        }
      } catch {
        void reader.cancel().catch(() => {});
        return NextResponse.json({ detail: deadline.aborted ? 'BODY_TIMEOUT' : 'BODY_INTERRUPTED' },
          { status: deadline.aborted ? 408 : 400 });
      } finally {
        deadline.removeEventListener('abort', rejectDeadline);
      }
    }
    body = Buffer.concat(chunks).toString('utf8') || '{}';
    try { JSON.parse(body); } catch {
      return NextResponse.json({ detail: 'INVALID_JSON' }, { status: 400 });
    }
    headers['Content-Type'] = 'application/json';
    headers.Origin = origin;
  }
  try {
    const response = await fetch(new URL(route, backend), {
      method: request.method, headers, body, cache: 'no-store',
      redirect: 'error', signal: AbortSignal.timeout(route === 'simulation' ? 60000 : 20000),
    });
    const result = await response.text();
    const output = new NextResponse(result, { status: response.status, headers: {
      'Content-Type': 'application/json', 'Cache-Control': 'no-store',
    } });
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) output.headers.set('set-cookie', setCookie);
    return output;
  } catch (error) {
    const timeout = error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name);
    return NextResponse.json({ detail: timeout ? 'BACKEND_TIMEOUT' : 'BACKEND_UNAVAILABLE' },
      { status: timeout ? 504 : 503, headers: { 'Cache-Control': 'no-store' } });
  }
}
export { proxy as GET, proxy as POST, proxy as DELETE };
