import { readFileSync } from 'node:fs';
import { type APIRequestContext, type Browser, type Page, expect, test } from '@playwright/test';

type TestUser = { key: string; email: string; password: string };
const usersFile = process.env.R1_E2E_USERS;
const users: Record<string, TestUser> = usersFile
  ? Object.fromEntries((JSON.parse(readFileSync(usersFile, 'utf8')).users as TestUser[]).map(u => [u.key, u]))
  : {};
const API = process.env.R1_API_URL ?? 'http://127.0.0.1:8100';
const AUTH = process.env.R1_AUTH_URL ?? 'http://127.0.0.1:54999';
const run = `${Date.now().toString(36).slice(-5).toUpperCase()}B`;
const shots = 'artifacts/r1-e2e-screens';

test.skip(!usersFile, 'R1_E2E_USERS is not set; see e2e/r1/README.md');

async function signIn(page: Page, user: TestUser) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
}

async function session(browser: Browser, user: TestUser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, user);
  return { context, page };
}

/** A real access token for a user, obtained the same way the browser obtains one. */
async function tokenFor(request: APIRequestContext, user: TestUser): Promise<string> {
  const response = await request.post(`${AUTH}/auth/v1/token?grant_type=password`, { data: { email: user.email, password: user.password } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token;
}

const figure = (page: Page, label: string) => page.locator(`dd[data-figure="${label}"]`);
const allocationsTable = (page: Page) => page.getByRole('table', { name: 'Supplier allocations' });

test.describe.serial('R1 consent, invalid transitions and boundaries', () => {
  let orderPath = '';
  const buyerName = `Montego Bay Kitchens ${run}`;
  const farmers = [`Lorna Campbell ${run}`, `Winston Hall ${run}`];

  test('set up an order with proposed supply through the UI', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/buyers');
    await page.getByLabel('Buyer name').fill(buyerName);
    await page.getByLabel('Buyer type').fill('Hotel group');
    await page.getByLabel('Delivery destination').fill('Montego Bay');
    await page.getByRole('button', { name: 'Add buyer' }).click();
    await expect(page.getByRole('status')).toHaveText(`Saved ${buyerName}.`);
    await page.goto('/suppliers');
    for (const [name, parish, qty] of [[farmers[0], 'St. James', '500'], [farmers[1], 'Westmoreland', '400']]) {
      await page.getByLabel('Farmer name').fill(name);
      await page.getByLabel('Parish').fill(parish);
      await page.getByRole('button', { name: 'Add supplier' }).click();
      await expect(page.getByRole('list', { name: 'Suppliers' })).toContainText(name);
      await page.getByRole('combobox', { name: 'Supplier', exact: true }).selectOption({ label: `${name} (${parish})` });
      await page.getByLabel('Crop').selectOption({ label: 'Scotch bonnet pepper' });
      await page.getByLabel('Harvest from').fill('2026-11-20');
      await page.getByLabel('Harvest to').fill('2026-12-10');
      await page.getByLabel('Expected harvest (kg)').fill(qty);
      await page.getByLabel('Available now (kg)').fill(qty);
      await page.getByLabel('Farmgate price (J$/kg)').fill('640');
      await page.getByLabel('How you received this').fill('farm visit');
      await page.getByLabel('Attestation').fill('signed declaration form');
      await page.getByRole('button', { name: 'Record lot' }).click();
      await expect(page.getByRole('status')).toContainText(`for ${name} as declared`);
    }
    await page.goto('/orders/new');
    await page.getByLabel('Buyer').selectOption({ label: buyerName });
    await page.getByLabel('Crop').selectOption({ label: 'Scotch bonnet pepper' });
    await page.getByLabel('Required quantity (kg)').fill('730');
    await page.getByLabel('Delivery from').fill('2026-12-01');
    await page.getByLabel('Delivery to').fill('2026-12-12');
    await page.getByRole('button', { name: 'Create order' }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    orderPath = new URL(page.url()).pathname;
    await page.getByRole('button', { name: 'Propose supply' }).click();
    await expect(allocationsTable(page)).toContainText('Proposed');
    // Locked after planning: the edit control is gone and the reason is stated.
    await expect(page.getByRole('button', { name: 'Edit terms' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Order terms' })).toContainText('terms are locked');
  });

  test('a supplier decline and a coordinator withdrawal are recorded and commit nothing', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    const table = allocationsTable(page);
    const ask = table.getByRole('button', { name: /^Ask .+ commitment$/ }).first();
    const who = (await ask.getAttribute('aria-label'))!.replace(/^Ask /, '').replace(/ commitment$/, '');
    await ask.click();
    await table.getByRole('button', { name: `Record response for ${who} commitment` }).click();
    const form = page.getByRole('form', { name: `Supplier response for ${who}` });
    await form.getByLabel('Supplier decision').selectOption('DECLINED');
    await form.getByLabel('How the supplier told you').fill('phone call');
    await form.getByRole('button', { name: 'Save supplier response' }).click();
    await expect(table.getByRole('row', { name: new RegExp(`${who}.*Commitment`) }).first()).toContainText('Declined');
    await expect(figure(page, 'Committed')).toHaveText('0 kg');

    const withdraw = table.getByRole('button', { name: /^Withdraw .+ standby$/ }).first();
    const standbyWho = (await withdraw.getAttribute('aria-label'))!.replace(/^Withdraw /, '').replace(/ standby$/, '');
    await withdraw.click();
    await expect(table.getByRole('row', { name: new RegExp(`${standbyWho}.*Standby`) }).first()).toContainText('Withdrawn');
    await expect(figure(page, 'Authorized standby')).toHaveText('0 kg');
    const history = page.getByRole('list', { name: 'Order history' });
    await expect(history).toContainText('Supplier declined');
    await expect(history).toContainText('Solicitation withdrawn');
    await page.screenshot({ path: `${shots}/06-decline-and-withdraw.png`, fullPage: true });
  });

  test('an order with accepted supply is not cancelled directly; a request needs the supplier’s agreement and nothing changes', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    const table = allocationsTable(page);
    const ask = table.getByRole('button', { name: /^Ask .+ commitment$/ }).first();
    const who = (await ask.getAttribute('aria-label'))!.replace(/^Ask /, '').replace(/ commitment$/, '');
    await ask.click();
    await table.getByRole('button', { name: `Record response for ${who} commitment` }).click();
    const form = page.getByRole('form', { name: `Supplier response for ${who}` });
    await form.getByLabel('How the supplier told you').fill('phone call');
    await form.getByRole('button', { name: 'Save supplier response' }).click();
    await expect(figure(page, 'Committed')).not.toHaveText('0 kg');

    // R1 WP4 (P1): with supplier commitments a coordinator can only request cancellation.
    await expect(page.getByRole('form', { name: 'Cancel order' })).toHaveCount(0);
    await page.getByText('Request cancellation').click();
    const request = page.getByRole('form', { name: 'Request cancellation' });
    await request.getByLabel('Reason').fill('buyer withdrew');
    await request.getByLabel("Buyer's instruction or evidence").fill('email from the buyer');
    await request.getByRole('button', { name: 'Submit cancellation request' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cancellation requested' })).toBeVisible();
    // No supplier has agreed to be released, so the agent escalates instead of proposing.
    await expect(page.getByRole('region', { name: 'Recovery', exact: true })).toContainText('needs supplier agreement first', { timeout: 30_000 });
    await page.reload();
    await expect(page.getByRole('region', { name: 'Order terms' })).not.toContainText('Cancelled:');
    await expect(figure(page, 'Committed')).not.toHaveText('0 kg');
    await page.screenshot({ path: `${shots}/07-cancel-refused-with-commitments.png`, fullPage: true });
  });

  test("another organization's real session token cannot read or change this order", async ({ page, request }) => {
    const orderId = orderPath.split('/').pop()!;
    const own = await tokenFor(request, users.coordinator_a);
    const before = await (await request.get(`${API}/requirements/${orderId}/assurance`, { headers: { Authorization: `Bearer ${own}` } })).json();
    const allocationId = before.allocations[0].id as string;

    const outsider = await tokenFor(request, users.coordinator_b);
    const auth = { Authorization: `Bearer ${outsider}` };
    const attempts: Array<[string, string, unknown]> = [
      ['GET', `/requirements/${orderId}`, undefined],
      ['GET', `/requirements/${orderId}/assurance`, undefined],
      ['GET', `/requirements/${orderId}/history`, undefined],
      ['PATCH', `/requirements/${orderId}`, { expected_version: 1, notes: 'tampered' }],
      ['POST', `/requirements/${orderId}/cancel`, { reason: 'tampered' }],
      ['POST', `/requirements/${orderId}/plan`, undefined],
      ['POST', `/allocations/${allocationId}/solicit`, {}],
      ['POST', `/allocations/${allocationId}/withdraw`, { reason: 'tampered' }],
      ['POST', `/allocations/${allocationId}/responses`, { decision: 'ACCEPTED', attestation_method: 'tampered' }],
      ['GET', `/allocations/${allocationId}/consents`, undefined],
    ];
    for (const [method, path, data] of attempts) {
      const response = await request.fetch(`${API}${path}`, { method, data, headers: { ...auth, 'Idempotency-Key': `attack-${run}-${path}` } });
      expect(response.status(), `${method} ${path}`).toBe(404);
    }
    const list = await (await request.get(`${API}/requirements`, { headers: auth })).text();
    expect(list).not.toContain(orderId);

    // The owner's view is unchanged after the attempts.
    const after = await (await request.get(`${API}/requirements/${orderId}/assurance`, { headers: { Authorization: `Bearer ${own}` } })).json();
    expect(after.allocations).toEqual(before.allocations);
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    await expect(page.getByRole('region', { name: 'Order terms' })).not.toContainText('tampered');
  });

  test('a change in one session appears in an independent session', async ({ browser }) => {
    const first = await session(browser, users.coordinator_a);
    const second = await session(browser, users.colleague_a);
    await second.page.goto('/buyers');
    const newcomer = `Ocho Rios Resort ${run}`;
    await expect(second.page.getByRole('list', { name: 'Buyers' })).not.toContainText(newcomer);
    await first.page.goto('/buyers');
    await first.page.getByLabel('Buyer name').fill(newcomer);
    await first.page.getByLabel('Buyer type').fill('Hotel');
    await first.page.getByLabel('Delivery destination').fill('Ocho Rios');
    await first.page.getByRole('button', { name: 'Add buyer' }).click();
    await expect(first.page.getByRole('status')).toHaveText(`Saved ${newcomer}.`);
    await second.page.reload();
    await expect(second.page.getByRole('list', { name: 'Buyers' })).toContainText(newcomer);
    await first.context.close();
    await second.context.close();
  });
});
