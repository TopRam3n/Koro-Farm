import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// WP4: the spec section 6 story through the real UI, in independent sessions. 730 kg ordered, 725 kg received,
// 705 kg accepted and 20 kg rejected; 705 kg delivered and confirmed by the buyer in their own account. The order is
// reconciled but never shown as 730 kg delivered or as completed; a procurement manager closes it with the
// documented 25 kg variance, which every later session still sees.
type TestUser = { key: string; email: string; password: string; buyer_name: string | null };
const usersFile = process.env.R1_E2E_USERS;
const users: Record<string, TestUser> = usersFile
  ? Object.fromEntries((JSON.parse(readFileSync(usersFile, 'utf8')).users as TestUser[]).map(u => [u.key, u]))
  : {};
const run = Date.now().toString(36).slice(-5).toUpperCase();
const shots = 'artifacts/r1-e2e-screens';

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

const figure = (page: Page, label: string) => page.getByLabel('Fulfilment quantities').locator(`dd[data-figure="${label}"]`);

test.describe.serial('WP4 fulfilment, buyer confirmation and close-out', () => {
  const farmer = `Marcia Campbell ${run}`;
  const site = `Linstead Packhouse ${run}`;
  const reference = `PL-${run}`;
  let orderPath = '';

  test('a 730 kg order is committed through the supplier’s recorded decision', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/suppliers');
    await page.getByLabel('Farmer name').fill(farmer);
    await page.getByLabel('Parish').fill('St. Catherine');
    await page.getByRole('button', { name: 'Add supplier' }).click();
    await expect(page.getByRole('status')).toHaveText(`Saved supplier ${farmer}.`);
    await page.getByRole('combobox', { name: 'Supplier', exact: true }).selectOption({ label: `${farmer} (St. Catherine)` });
    await page.getByLabel('Crop').selectOption({ label: 'Plantain' });
    await page.getByLabel('Expected grade').selectOption('A');
    await page.getByLabel('Harvest from').fill('2026-11-20');
    await page.getByLabel('Harvest to').fill('2026-12-10');
    await page.getByLabel('Expected harvest (kg)').fill('800');
    await page.getByLabel('Available now (kg)').fill('760');
    await page.getByLabel('Farmgate price (J$/kg)').fill('180');
    await page.getByLabel('How you received this').fill('farm visit');
    await page.getByLabel('Attestation').fill('signed declaration form');
    await page.getByRole('button', { name: 'Record lot' }).click();
    await expect(page.getByRole('status')).toContainText(`for ${farmer} as declared`);

    await page.goto('/fulfilment/sites');
    const add = page.getByRole('form', { name: 'Add a site' });
    await add.getByLabel('Name').fill(site);
    await add.getByLabel('Type').fill('packhouse');
    await add.getByLabel('Parish').fill('St. Catherine');
    await add.getByRole('button', { name: 'Add site' }).click();
    await expect(page.getByRole('list', { name: 'Fulfilment sites' })).toContainText(site);

    await page.goto('/orders/new');
    await page.getByLabel('Buyer').selectOption({ label: users.buyer_a.buyer_name! });
    await page.getByLabel('Crop').selectOption({ label: 'Plantain' });
    await page.getByLabel('Grade').selectOption('A');
    await page.getByLabel('Required quantity (kg)').fill('730');
    await page.getByLabel('Delivery from').fill('2026-12-01');
    await page.getByLabel('Delivery to').fill('2026-12-12');
    await page.getByRole('button', { name: 'Create order' }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    orderPath = new URL(page.url()).pathname;

    await page.getByRole('region', { name: 'Supply' }).getByRole('button', { name: 'Propose supply' }).click();
    const table = page.getByRole('table', { name: 'Supplier allocations' });
    const label = `${farmer} commitment`;
    await table.getByRole('button', { name: `Ask ${label}`, exact: true }).click();
    await table.getByRole('button', { name: `Record response for ${label}`, exact: true }).click();
    const form = page.getByRole('form', { name: `Supplier response for ${farmer}` });
    await form.getByLabel('How the supplier told you').fill('phone call with farmer');
    await form.getByRole('button', { name: 'Save supplier response' }).click();
    await expect(form).toHaveCount(0);
    await expect(page.locator('dd[data-figure="Committed"]')).toHaveText('730 kg');
  });

  test('the warehouse records 725 kg received, 705 kg accepted and 20 kg rejected, then ships and delivers 705 kg', async ({ browser }) => {
    const { context, page } = await freshSession(browser, users.warehouse_a);
    await page.goto(orderPath);
    await page.getByText('Record a receipt').click();
    const receipt = page.getByRole('form', { name: 'Record a receipt' });
    await receipt.getByLabel('Supplier commitment').selectOption({ index: 1 });
    await receipt.getByLabel('Fulfilment site').selectOption({ label: `${site}, St. Catherine` });
    await receipt.getByLabel('Received (kg)').fill('725');
    await receipt.getByLabel('Received at').fill('2026-12-02T08:30');
    await receipt.getByLabel('Receipt evidence').fill(`weighbridge ticket ${run}`);
    await receipt.getByRole('button', { name: 'Save receipt' }).click();
    await expect(figure(page, 'Received')).toHaveText('725 kg');
    await expect(figure(page, 'Accepted')).toHaveText('0 kg'); // receipt is not acceptance

    await page.getByRole('table', { name: 'Receipts' }).getByRole('button', { name: 'Record grading' }).click();
    const grading = page.getByRole('form', { name: `Grading for ${farmer}` });
    await grading.getByLabel('Accepted (kg)').fill('705');
    await grading.getByLabel('Rejected (kg)').fill('20');
    await grading.getByLabel('Grade').selectOption('A');
    await grading.getByLabel('Rejection reason').fill('bruised fingers');
    await grading.getByRole('button', { name: 'Save grading' }).click();
    await expect(figure(page, 'Accepted')).toHaveText('705 kg');
    await expect(figure(page, 'Rejected')).toHaveText('20 kg');

    const create = page.getByRole('form', { name: 'New shipment' });
    await create.getByLabel('From site').selectOption({ label: site });
    await create.getByLabel('Shipment reference').fill(reference);
    await create.getByRole('button', { name: 'New shipment' }).click();
    const shipment = page.locator('[data-shipment]').filter({ hasText: reference });
    await shipment.getByRole('button', { name: `Add ${farmer} 705 kg` }).click();
    await shipment.getByRole('button', { name: 'Dispatch' }).click();
    await expect(shipment).toHaveAttribute('data-shipment', 'DISPATCHED');
    await shipment.getByRole('button', { name: 'Record delivery' }).click();
    const delivery = page.getByRole('form', { name: `Delivery for ${reference}` });
    await delivery.getByLabel('Delivered (kg)').fill('705');
    await delivery.getByLabel('Delivered at').fill('2026-12-03T11:00');
    await delivery.getByRole('button', { name: 'Save delivery' }).click();
    await expect(figure(page, 'Delivered')).toHaveText('705 kg');
    await expect(figure(page, 'Buyer-confirmed')).toHaveText('0 kg');
    await expect(shipment).toContainText('Not confirmed by the buyer');
    await context.close();
  });

  test('the buyer confirms 705 kg in their own account and cannot confirm more than was delivered', async ({ browser }) => {
    const { context, page } = await freshSession(browser, users.buyer_a);
    await page.goto('/deliveries');
    const item = page.locator('[data-delivery]').filter({ hasText: reference });
    await expect(item).toContainText('Recorded as delivered: 705 kg');
    await item.getByRole('button', { name: 'Confirm what I received' }).click();
    const form = item.getByRole('form', { name: 'Confirm delivery' });
    await expect(form.getByLabel(/Quantity you received/)).toHaveAttribute('max', '705');
    await form.getByLabel(/Quantity you received/).fill('705');
    await form.getByRole('button', { name: 'Confirm' }).click();
    await expect(item).toContainText('Confirmed by the buyer in their account');
    await page.screenshot({ path: `${shots}/20-buyer-confirms-delivery.png`, fullPage: true });
    await context.close();
  });

  test('the coordinator reconciles; the order is never shown as 730 kg delivered or as completed', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    await page.getByRole('form', { name: 'Reconcile' }).getByRole('button', { name: 'Reconcile' }).click();
    const versions = page.getByRole('list', { name: 'Reconciliation versions' });
    await expect(versions).toContainText('Version 1');
    await expect(figure(page, 'Delivered')).toHaveText('705 kg');
    await expect(figure(page, 'Buyer-confirmed')).toHaveText('705 kg');
    await expect(page.getByLabel('Order outcome')).toContainText('Reconciled, not closed');
    await expect(page.getByRole('list', { name: 'Why it cannot be completed' })).toContainText('buyer-confirmed 705 kg of 730 kg required');
    await expect(page.getByRole('button', { name: 'Close as completed' })).toHaveCount(0);
    // A coordinator cannot accept a variance; the server refuses and says why.
    const close = page.getByRole('form', { name: 'Close with an accepted variance' });
    await close.getByLabel('Documented reason for accepting the difference').fill('short harvest');
    await close.getByRole('button', { name: 'Close with variance' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'variance' })).toBeVisible();
    await page.screenshot({ path: `${shots}/21-reconciled-not-completed.png`, fullPage: true });
  });

  test('a procurement manager closes it with the documented variance, and every session keeps seeing it', async ({ browser }) => {
    const manager = await freshSession(browser, users.colleague_a);
    await manager.page.goto(orderPath);
    const close = manager.page.getByRole('form', { name: 'Close with an accepted variance' });
    await close.getByLabel('Documented reason for accepting the difference').fill('20 kg rejected at grading and 5 kg never harvested; buyer informed');
    await close.getByRole('button', { name: 'Close with variance' }).click();
    await expect(manager.page.getByLabel('Order outcome')).toContainText('Closed with variance');
    await expect(manager.page.getByRole('note')).toContainText('25 kg short of the order');
    await manager.page.reload();
    await expect(manager.page.getByLabel('Order outcome')).toContainText('Closed with variance');
    await expect(figure(manager.page, 'Delivered')).toHaveText('705 kg');
    await manager.page.screenshot({ path: `${shots}/22-closed-with-variance.png`, fullPage: true });
    await manager.context.close();

    const coordinator = await freshSession(browser, users.coordinator_a);
    await coordinator.page.goto(orderPath);
    await expect(coordinator.page.getByLabel('Order outcome')).toContainText('Closed with variance');
    await expect(figure(coordinator.page, 'Received')).toHaveText('725 kg');
    await expect(figure(coordinator.page, 'Accepted')).toHaveText('705 kg');
    await expect(figure(coordinator.page, 'Released')).toHaveText('5 kg');
    await coordinator.context.close();
  });

  test('another organization sees none of it', async ({ browser }) => {
    const outsider = await freshSession(browser, users.coordinator_b);
    await outsider.page.goto(orderPath);
    await expect(outsider.page.getByRole('alert')).toBeVisible();
    await expect(outsider.page.getByText(farmer)).toHaveCount(0);
    await outsider.context.close();
  });
});
