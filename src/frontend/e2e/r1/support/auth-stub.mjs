// Test-only stand-in for the few Supabase Auth endpoints KoroFarm uses, so browser E2E can sign in
// real test users without creating accounts in a hosted Supabase project.
//
// The app code is unchanged: the login page calls supabase-js signInWithPassword against this URL, and the
// backend verifies bearer tokens by calling GET /auth/v1/user here, exactly as it does against Supabase.
// Users come from the JSON file written by src/backend/scripts/seed_e2e.py. Never run outside tests.
//
// Usage: node auth-stub.mjs <users.json> [port]
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';

// Fail closed: run only when explicitly opted in for tests, never under a production-like environment.
const refusal = process.env.KOROFARM_E2E_AUTH_STANDIN !== '1'
  ? 'KOROFARM_E2E_AUTH_STANDIN=1 is required (test-only auth stand-in)'
  : process.env.NODE_ENV === 'production'
    ? 'NODE_ENV=production: the test-only auth stand-in will not run'
    : process.env.APP_ENV && process.env.APP_ENV.trim().toLowerCase() !== 'test'
      ? `APP_ENV=${process.env.APP_ENV}: the test-only auth stand-in runs only with APP_ENV unset or test`
      : null;
if (refusal) {
  console.error(`Refusing to start: ${refusal}`);
  process.exit(78);
}

const [usersFile, portArg] = process.argv.slice(2);
if (!usersFile) throw new Error('usage: node auth-stub.mjs <users.json> [port]');
const port = Number(portArg ?? 54999);
const users = JSON.parse(readFileSync(usersFile, 'utf8')).users;
const sessions = new Map(); // token -> user id

const publicUser = user => ({
  id: user.id, aud: 'authenticated', role: 'authenticated', email: user.email, email_confirmed_at: user.created_at,
  app_metadata: { provider: 'email', providers: ['email'] }, user_metadata: { display_name: user.display_name },
  created_at: user.created_at, updated_at: user.created_at,
});

function issue(user) {
  const access = `e2e-access-${randomBytes(24).toString('hex')}`;
  const refresh = `e2e-refresh-${randomBytes(24).toString('hex')}`;
  sessions.set(access, user.id);
  sessions.set(refresh, user.id);
  const expiresIn = 3600;
  return { access_token: access, token_type: 'bearer', expires_in: expiresIn, expires_at: Math.floor(Date.now() / 1000) + expiresIn,
           refresh_token: refresh, user: publicUser(user) };
}

function send(res, origin, status, body) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': origin ?? '*',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info, x-supabase-api-version',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  });
  res.end(body === undefined ? '' : JSON.stringify(body));
}

const readBody = req => new Promise(resolve => {
  let data = '';
  req.on('data', chunk => { data += chunk; });
  req.on('end', () => { try { resolve(data ? JSON.parse(data) : {}); } catch { resolve({}); } });
});

createServer(async (req, res) => {
  const origin = req.headers.origin;
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  if (req.method === 'OPTIONS') return send(res, origin, 204);
  if (url.pathname === '/health') return send(res, origin, 200, { status: 'ok' });
  if (req.method === 'POST' && url.pathname === '/auth/v1/token') {
    const body = await readBody(req);
    const grant = url.searchParams.get('grant_type');
    if (grant === 'password') {
      const user = users.find(u => u.email === body.email && u.password === body.password);
      return user ? send(res, origin, 200, issue(user))
                  : send(res, origin, 400, { error: 'invalid_grant', error_description: 'Invalid login credentials', msg: 'Invalid login credentials' });
    }
    if (grant === 'refresh_token') {
      const user = users.find(u => u.id === sessions.get(body.refresh_token));
      return user ? send(res, origin, 200, issue(user)) : send(res, origin, 400, { error: 'invalid_grant', msg: 'Invalid refresh token' });
    }
    return send(res, origin, 400, { error: 'unsupported_grant_type' });
  }
  if (req.method === 'GET' && url.pathname === '/auth/v1/user') {
    const token = (req.headers.authorization ?? '').replace(/^Bearer\s+/i, '');
    const user = users.find(u => u.id === sessions.get(token));
    return user ? send(res, origin, 200, publicUser(user)) : send(res, origin, 401, { msg: 'invalid token' });
  }
  if (req.method === 'POST' && url.pathname === '/auth/v1/logout') {
    sessions.delete((req.headers.authorization ?? '').replace(/^Bearer\s+/i, ''));
    return send(res, origin, 204);
  }
  return send(res, origin, 404, { msg: `not implemented in E2E auth stand-in: ${req.method} ${url.pathname}` });
}).listen(port, '127.0.0.1', () => console.log(`E2E auth stand-in listening on 127.0.0.1:${port} with ${users.length} test users`));
