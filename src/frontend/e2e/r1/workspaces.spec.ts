import { readFileSync } from 'node:fs';
import { type Page, expect, test } from '@playwright/test';

// Formerly e2e/enterprise.spec.ts (which ran unauthenticated against the retired demo setup). The same honesty
// checks now run as a signed-in user against the live API, with an order created for this run.
type TestUser = { key: string; email: string; password: string };
const usersFile = process.env.R1_E2E_USERS;
const users: Record<string, TestUser> = usersFile
  ? Object.fromEntries((JSON.parse(readFileSync(usersFile, 'utf8')).users as TestUser[]).map(u => [u.key, u]))
  : {};
const API = process.env.R1_API_URL ?? 'http://127.0.0.1:8100';
const AUTH = process.env.R1_AUTH_URL ?? 'http://127.0.0.1:54999';
const run = `${Date.now().toString(36).slice(-5).toUpperCase()}W`;

test.skip(!usersFile, 'R1_E2E_USERS is not set; see e2e/r1/README.md');

const routes = [
  ['/', 'My Work'], ['/command-center', 'Supply Assurance Control Room'], ['/programmes', 'Programmes'],
  ['/demand', 'Demand'], ['/supply', 'Supply Network'], ['/assurance', 'Supply Assurance Control Room'],
  ['/scenario-lab', 'KoroFarm Scenario Lab'], ['/fulfilment', 'Fulfilment Center'], ['/network', 'Network Intelligence'],
  ['/compliance', 'Compliance Registry'], ['/traceability', 'Traceability Explorer'], ['/trade-evidence', 'Trade Evidence'],
  ['/analytics', 'Analytics'], ['/agent-operations', 'Agent Operations'], ['/activity', 'Activity & Audit'],
  ['/integrations', 'Integrations'], ['/settings', 'Settings'],
] as const;

async function signIn(page: Page, user: TestUser) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
}

test.beforeAll(async ({ request }) => {
  // Give the overview workspaces an order of this run to show.
  const login = await request.post(`${AUTH}/auth/v1/token?grant_type=password`, { data: { email: users.coordinator_a.email, password: users.coordinator_a.password } });
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const buyer = await (await request.post(`${API}/buyers`, { headers, data: { name: `Workspace Check Hotel ${run}`, buyer_type: 'Hotel', destination: 'Negril' } })).json();
  const order = await request.post(`${API}/requirements`, { headers, data: { buyer_id: buyer.id, crop: 'SCOTCH_BONNET', grade: 'A', required_quantity_kg: '120', delivery_window_start: '2026-12-01', delivery_window_end: '2026-12-12' } });
  expect(order.status()).toBe(201);
  // Committed supply for this order, obtained the legitimate way: declared lot, plan, solicitation, recorded acceptance.
  const orderId = (await order.json()).id;
  const farmer = await (await request.post(`${API}/farmers`, { headers, data: { name: `Workspace Farmer ${run}`, parish: 'Hanover' } })).json();
  const lot = await request.post(`${API}/production-lots`, { headers, data: { farmer_id: farmer.id, crop: 'SCOTCH_BONNET', harvest_start: '2026-11-20', harvest_end: '2026-12-10', expected_quantity_kg: '200', available_quantity_kg: '200', quality_grade_estimate: 'A', provenance_source: 'phone call with farmer', attestation_method: 'verbal', farmgate_price_per_kg_jmd: '600' } });
  expect(lot.status()).toBe(201);
  expect((await request.post(`${API}/requirements/${orderId}/plan`, { headers: { ...headers, 'Idempotency-Key': `plan-${run}` } })).status()).toBe(201);
  const supply = await (await request.get(`${API}/requirements/${orderId}/assurance`, { headers })).json();
  const commitment = supply.allocations.find((a: { role: string; farmer_id: string }) => a.role === 'COMMITTED' && a.farmer_id === farmer.id);
  expect((await request.post(`${API}/allocations/${commitment.id}/solicit`, { headers: { ...headers, 'Idempotency-Key': `sol-${run}` }, data: {} })).status()).toBe(200);
  expect((await request.post(`${API}/allocations/${commitment.id}/responses`, { headers: { ...headers, 'Idempotency-Key': `acc-${run}` }, data: { decision: 'ACCEPTED', attestation_method: 'phone call with farmer' } })).status()).toBe(200);
});

test('workspace route map is navigable and honest for a signed-in user', async ({ page }) => {
  await signIn(page, users.coordinator_a);
  for (const [route, heading] of routes) {
    await page.goto(route);
    await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.locator('body')).not.toContainText(/guaranteed delivery|credit score/i);
  }
});

test('command palette supports keyboard navigation discovery', async ({ page }) => {
  await signIn(page, users.coordinator_a);
  await page.goto('/command-center');
  const trigger = page.getByRole('button', { name: /Search or jump to/ });
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+K');
  await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible();
  await page.getByPlaceholder(/Search workspaces/).fill('scenario');
  await expect(page.getByRole('dialog', { name: 'Command palette' }).getByRole('link', { name: 'Scenario Lab' })).toBeVisible();
});

test('scenario lab remains visibly non-persistent', async ({ page }) => {
  await signIn(page, users.coordinator_a);
  await page.goto('/scenario-lab');
  await expect(page.getByText('SIMULATION', { exact: true })).toBeVisible();
  await expect(page.getByText('No live writes')).toBeVisible();
  const slider = page.getByLabel('Quantity impact');
  const max = Number(await slider.getAttribute('max'));
  expect(max).toBeGreaterThan(0);
  const value = String(Math.max(1, Math.floor(max / 2)) === 80 ? 79 : Math.max(1, Math.floor(max / 2)));
  await slider.fill(value);
  await expect(page.getByText(`${value} kg`, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(`${value} kg`, { exact: true })).toHaveCount(0);  // nothing was written
});
