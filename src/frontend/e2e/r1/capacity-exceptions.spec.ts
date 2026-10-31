import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// WP2: a farmer's capacity cut reaches the coordinator's open order page through the outbox and the exception
// worker (python -m src.backend.app.worker), without a reload. Requires the worker to be running; see README.md.
type TestUser = { key: string; email: string; password: string; farmer_name: string | null; farmer_parish: string | null };
const usersFile = process.env.R1_E2E_USERS;
const users: Record<string, TestUser> = usersFile
  ? Object.fromEntries((JSON.parse(readFileSync(usersFile, 'utf8')).users as TestUser[]).map(u => [u.key, u]))
  : {};
const run = Date.now().toString(36).slice(-5).toUpperCase();
const shots = 'artifacts/r1-e2e-screens';
// Polling interval (5 s) plus worker poll (2 s), with headroom for a slow CI runner.
const LIVE = { timeout: 30_000 };

test.skip(!usersFile, 'R1_E2E_USERS is not set; see e2e/r1/README.md');

async function signIn(page: Page, user: TestUser) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
}

async function freshSession(browser: Browser, user: TestUser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, user);
  return { context, page };
}

async function farmerReports(browser: Browser, quantity: string, shot?: string) {
  const farmer = await freshSession(browser, users.farmer_a);
  await farmer.page.goto('/farmer');
  await farmer.page.getByLabel('Kilograms you can supply now').fill(quantity);
  await farmer.page.getByRole('button', { name: 'Report what I can supply' }).click();
  await expect(farmer.page.getByRole('status').filter({ hasText: 'Report recorded' })).toBeVisible();
  if (shot) await farmer.page.screenshot({ path: `${shots}/${shot}`, fullPage: true });
  await farmer.context.close();
}

const figure = (page: Page, label: string) => page.locator(`dd[data-figure="${label}"]`);

test.describe.serial('WP2 capacity reports and supply exceptions', () => {
  let orderPath = '';
  const buyerName = `Ocho Rios Spice Traders ${run}`;

  test('a farmer sees the request and its reply deadline in the portal and accepts it there', async ({ browser, page }) => {
    const farmer = users.farmer_a;
    await signIn(page, users.coordinator_a);

    await page.goto('/buyers');
    await page.getByLabel('Buyer name').fill(buyerName);
    await page.getByLabel('Buyer type').fill('Exporter');
    await page.getByLabel('Delivery destination').fill('Port of Kingston');
    await page.getByRole('button', { name: 'Add buyer' }).click();
    await expect(page.getByRole('status')).toHaveText(`Saved ${buyerName}.`);

    await page.goto('/suppliers');
    await page.getByRole('combobox', { name: 'Supplier', exact: true }).selectOption({ label: `${farmer.farmer_name} (${farmer.farmer_parish})` });
    await page.getByLabel('Crop').selectOption({ label: 'Ginger' });
    await page.getByLabel('Expected grade').selectOption('A');
    await page.getByLabel('Harvest from').fill('2026-11-20');
    await page.getByLabel('Harvest to').fill('2026-12-10');
    await page.getByLabel('Expected harvest (kg)').fill('400');
    await page.getByLabel('Available now (kg)').fill('300');
    await page.getByLabel('Farmgate price (J$/kg)').fill('540');
    await page.getByLabel('How you received this').fill('farm visit');
    await page.getByLabel('Attestation').fill('signed declaration form');
    await page.getByRole('button', { name: 'Record lot' }).click();
    await expect(page.getByRole('status')).toContainText(`for ${farmer.farmer_name} as declared`);

    await page.goto('/orders/new');
    await page.getByLabel('Buyer').selectOption({ label: buyerName });
    await page.getByLabel('Crop').selectOption({ label: 'Ginger' });
    await page.getByLabel('Grade').selectOption('A');
    await page.getByLabel('Required quantity (kg)').fill('300');
    await page.getByLabel('Delivery from').fill('2026-12-01');
    await page.getByLabel('Delivery to').fill('2026-12-12');
    await page.getByRole('button', { name: 'Create order' }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    orderPath = new URL(page.url()).pathname;

    await page.getByRole('region', { name: 'Supply' }).getByRole('button', { name: 'Propose supply' }).click();
    const allocations = page.getByRole('table', { name: 'Supplier allocations' });
    const who = `${farmer.farmer_name} commitment`;
    await allocations.getByRole('button', { name: `Ask ${who}`, exact: true }).click();
    const row = allocations.getByRole('row', { name: new RegExp(farmer.farmer_name!) }).first();
    await expect(row).toContainText('Awaiting supplier');
    await expect(row).toContainText('Reply by');  // 24-hour default: delivery is more than 48 hours away

    // The farmer answers for themselves; the coordinator's open page picks it up without a reload.
    const portal = await freshSession(browser, users.farmer_a);
    await portal.page.goto('/farmer');
    const nav = portal.page.getByRole('navigation', { name: 'Primary navigation' });
    await expect(nav.getByRole('link', { name: 'My harvest' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Orders' })).toHaveCount(0);  // farmers get the farmer navigation only
    const request = portal.page.getByRole('list', { name: 'Requests awaiting your answer' }).getByRole('listitem').filter({ hasText: buyerName });
    await expect(request).toContainText('Please reply by');
    await expect(request).toContainText('never taken as a yes or a no');
    await portal.page.screenshot({ path: `${shots}/09-farmer-request-with-deadline.png`, fullPage: true });
    await request.getByRole('button', { name: 'I can supply this' }).click();
    await expect(portal.page.getByText('No requests are waiting for your answer.')).toBeVisible();
    await portal.context.close();
    await expect(row).toContainText('Committed', LIVE);
    await expect(figure(page, 'Committed')).toHaveText('300 kg');
    await expect(figure(page, 'Exposed')).toHaveText('0 kg');
    await expect(page.getByRole('region', { name: 'Needs attention' })).toContainText('No open supply exceptions for this order.');
  });

  test('the farmer’s reduced capacity appears on the coordinator’s open page without a reload', async ({ browser, page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    await expect(figure(page, 'Committed')).toHaveText('300 kg');
    const navigations: string[] = [];
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations.push(frame.url()); });

    await farmerReports(browser, '180', '10-farmer-reports-reduced-capacity.png');

    // The commitment stands; the shortfall is reported separately.
    await expect(figure(page, 'Exposed')).toHaveText('120 kg', LIVE);
    await expect(figure(page, 'Committed')).toHaveText('300 kg');
    await expect(figure(page, 'Currently covered')).toHaveText('180 kg');
    const attention = page.getByRole('region', { name: 'Needs attention' });
    await expect(attention.locator('[data-exception="CAPACITY_SHORTFALL"]')).toContainText('120 kg', LIVE);
    await expect(page.getByRole('table', { name: 'Supplier allocations' })).toContainText('120 kg exposed');
    await expect(page.getByRole('region', { name: 'Supply' })).toContainText('nothing has been activated automatically');
    expect(navigations).toEqual([]);
    await page.screenshot({ path: `${shots}/11-exposure-and-exception-live.png`, fullPage: true });
  });

  test('the exception is listed for the organization, can be acknowledged, and cannot be closed by hand while exposed', async ({ browser, page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/exceptions');
    const item = page.locator('[data-exception="CAPACITY_SHORTFALL"]').filter({ hasText: buyerName });
    await expect(item).toBeVisible();
    await item.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(item).toContainText('Acknowledged');
    await item.getByRole('button', { name: 'Resolve…' }).click();
    await item.getByLabel(/What was done/).fill('Spoke with the buyer');
    await item.getByRole('button', { name: 'Resolve', exact: true }).click();
    await expect(item.getByRole('alert')).toBeVisible();
    await expect(item).toBeVisible();
    await page.screenshot({ path: `${shots}/12-needs-attention.png`, fullPage: true });

    const outsider = await freshSession(browser, users.coordinator_b);
    await outsider.page.goto('/exceptions');
    await expect(outsider.page.getByText('No open supply exceptions.')).toBeVisible();
    await expect(outsider.page.getByText(buyerName)).toHaveCount(0);
    await outsider.context.close();
  });

  test('restored capacity clears the exposure and closes the exception by itself', async ({ browser, page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    await expect(figure(page, 'Exposed')).toHaveText('120 kg');
    await farmerReports(browser, '300');
    await expect(figure(page, 'Exposed')).toHaveText('0 kg', LIVE);
    await expect(figure(page, 'Currently covered')).toHaveText('300 kg');
    await expect(page.getByRole('region', { name: 'Needs attention' })).toContainText('No open supply exceptions for this order.', LIVE);
    await expect(page.getByRole('list', { name: 'Order history' })).toContainText('Exception opened', LIVE);
    await expect(page.getByRole('list', { name: 'Order history' })).toContainText('Exception resolved', LIVE);
  });
});
