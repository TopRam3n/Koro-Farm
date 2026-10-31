import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// Release gate: real Supabase sign-in, session handling, cross-organization access and sign-out against a
// staging deployment. Never runs in CI and never against the E2E auth stand-in. See
// docs/product/STAGING_AUTH_VERIFICATION.md for the accounts and environment it needs.
type StagingUser = { email: string; password: string; organization_id: string };
const env = {
  baseUrl: process.env.STAGING_BASE_URL,
  apiUrl: process.env.STAGING_API_URL,
  supabaseUrl: process.env.STAGING_SUPABASE_URL,
  supabaseKey: process.env.STAGING_SUPABASE_PUBLISHABLE_KEY,
  usersFile: process.env.STAGING_USERS,
  orderA: process.env.STAGING_ORG_A_ORDER_ID,
};
const ready = Object.values(env).every(Boolean);
test.skip(!ready, 'Staging variables are not set; see docs/product/STAGING_AUTH_VERIFICATION.md');

const users: Record<'coordinator_a' | 'colleague_a' | 'coordinator_b', StagingUser> = ready ? JSON.parse(readFileSync(env.usersFile!, 'utf8')) : ({} as never);
const shots = 'artifacts/staging-auth';

test.beforeAll(() => {
  // Refuse to "pass" against anything that is not a hosted Supabase project over https.
  const url = new URL(env.supabaseUrl!);
  expect(url.protocol).toBe('https:');
  expect(['localhost', '127.0.0.1', '::1']).not.toContain(url.hostname);
});

async function signIn(page: Page, user: StagingUser) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
}

async function session(browser: Browser, user: StagingUser) {
  const context = await browser.newContext({ baseURL: env.baseUrl });
  const page = await context.newPage();
  await signIn(page, user);
  return { context, page };
}

/** The session supabase-js keeps in localStorage (sb-<project-ref>-auth-token). */
async function storedSession(page: Page): Promise<{ access_token: string; refresh_token: string } | null> {
  return page.evaluate(() => {
    const key = Object.keys(localStorage).find(k => k.startsWith('sb-') && k.endsWith('-auth-token'));
    return key ? JSON.parse(localStorage.getItem(key)!) : null;
  });
}

const claims = (jwt: string) => JSON.parse(Buffer.from(jwt.split('.')[1], 'base64url').toString('utf8'));

async function api(path: string, token: string, headers: Record<string, string> = {}) {
  return fetch(`${env.apiUrl}${path}`, { headers: { Authorization: `Bearer ${token}`, ...headers } });
}

test.describe.serial('staging: real Supabase authentication', () => {
  test('a wrong password is refused and no session is stored', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: env.baseUrl });
    const page = await context.newPage();
    await page.goto('/login');
    await page.getByLabel('Email').fill(users.coordinator_a.email);
    await page.getByLabel('Password').fill(`${users.coordinator_a.password}-wrong`);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForTimeout(3_000);
    expect(new URL(page.url()).pathname).toBe('/login');
    expect(await storedSession(page)).toBeNull();
    await context.close();
  });

  test('sign-in issues a session from the staging project that the API accepts for the right organization', async ({ browser }) => {
    const { context, page } = await session(browser, users.coordinator_a);
    const stored = await storedSession(page);
    expect(stored?.access_token).toBeTruthy();
    expect(String(claims(stored!.access_token).iss)).toContain(new URL(env.supabaseUrl!).host);
    const me = await api('/me', stored!.access_token);
    expect(me.status).toBe(200);
    expect((await me.json()).active_organization_id).toBe(users.coordinator_a.organization_id);
    await page.screenshot({ path: `${shots}/01-signed-in.png`, fullPage: true });
    await context.close();
  });

  test('the session survives a reload and a new tab, and a refreshed token is accepted', async ({ browser }) => {
    const { context, page } = await session(browser, users.coordinator_a);
    await page.goto('/orders');
    await page.reload();
    await expect(page).toHaveURL(/\/orders$/);
    const tab = await context.newPage();
    await tab.goto('/orders');
    await expect(tab).toHaveURL(/\/orders$/);

    // Exercise the refresh grant directly; this context is discarded afterwards because the old refresh token is rotated.
    const stored = (await storedSession(page))!;
    const refreshed = await fetch(`${env.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
      method: 'POST', headers: { apikey: env.supabaseKey!, 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: stored.refresh_token }),
    });
    expect(refreshed.status).toBe(200);
    const next = await refreshed.json();
    expect(next.access_token).not.toBe(stored.access_token);
    expect((await api('/me', next.access_token)).status).toBe(200);
    await context.close();
  });

  test('another organization cannot open, read or address this organization’s order', async ({ browser }) => {
    const colleague = await session(browser, users.colleague_a);
    const colleagueToken = (await storedSession(colleague.page))!.access_token;
    expect((await api(`/requirements/${env.orderA}`, colleagueToken)).status).toBe(200);  // control: same organization
    await colleague.context.close();

    const outsider = await session(browser, users.coordinator_b);
    await outsider.page.goto(`/orders/${env.orderA}`);
    await expect(outsider.page.getByRole('alert').filter({ hasText: 'requirement not found' })).toBeVisible();
    const token = (await storedSession(outsider.page))!.access_token;
    expect((await api(`/requirements/${env.orderA}`, token)).status).toBe(404);
    // Naming organization A explicitly must be refused: the membership check, not the header, decides.
    const forged = await api(`/requirements/${env.orderA}`, token, { 'X-Organization-ID': users.coordinator_a.organization_id });
    expect([403, 404]).toContain(forged.status);
    await outsider.page.screenshot({ path: `${shots}/02-other-organization-blocked.png`, fullPage: true });
    await outsider.context.close();
  });

  test('sign-out ends the session in the browser and at the API', async ({ browser }) => {
    const { context, page } = await session(browser, users.coordinator_a);
    const before = (await storedSession(page))!.access_token;
    await page.goto('/profile');
    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.waitForURL(url => url.pathname.startsWith('/login'));
    expect(await storedSession(page)).toBeNull();
    await page.goto('/orders');
    await page.waitForURL(url => url.pathname.startsWith('/login'));
    // The API checks every token with Supabase, so a signed-out session must no longer be accepted.
    expect((await api('/me', before)).status).toBe(401);
    await context.close();
  });
});
