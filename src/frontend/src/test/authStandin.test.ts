import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const stub = resolve(__dirname, '../../e2e/r1/support/auth-stub.mjs');
const users = join(mkdtempSync(join(tmpdir(), 'kf-standin-')), 'users.json');
writeFileSync(users, JSON.stringify({ users: [] }));

function clean(extra: Record<string, string>) {
  const env = { ...process.env };
  for (const key of ['KOROFARM_E2E_AUTH_STANDIN', 'NODE_ENV', 'APP_ENV']) delete env[key];
  return { ...env, ...extra };
}

describe('test-only auth stand-in fails closed', () => {
  it.each([
    [{}, 'KOROFARM_E2E_AUTH_STANDIN=1 is required'],
    [{ KOROFARM_E2E_AUTH_STANDIN: 'true' }, 'KOROFARM_E2E_AUTH_STANDIN=1 is required'],
    [{ KOROFARM_E2E_AUTH_STANDIN: '1', NODE_ENV: 'production' }, 'NODE_ENV=production'],
    [{ KOROFARM_E2E_AUTH_STANDIN: '1', APP_ENV: 'production' }, 'APP_ENV=production'],
    [{ KOROFARM_E2E_AUTH_STANDIN: '1', APP_ENV: 'demo' }, 'APP_ENV=demo'],
  ])('refuses to start with %o', (extra, reason) => {
    const result = spawnSync(process.execPath, [stub, users, '0'], { env: clean(extra), encoding: 'utf8', timeout: 15_000 });
    expect(result.status).toBe(78);
    expect(result.stderr).toContain(reason);
  });

  it('starts only when explicitly enabled, and only on loopback', async () => {
    const child = spawn(process.execPath, [stub, users, '0'], { env: clean({ KOROFARM_E2E_AUTH_STANDIN: '1', APP_ENV: 'test' }) });
    const line = await new Promise<string>((done, fail) => {
      child.stdout.on('data', chunk => done(String(chunk)));
      child.on('exit', code => fail(new Error(`exited ${code}`)));
      setTimeout(() => fail(new Error('no output')), 10_000);
    });
    child.kill();
    expect(line).toContain('listening on 127.0.0.1:');
  });
});
