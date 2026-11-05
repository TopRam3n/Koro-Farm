import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// WP4: the spec section 6 story through the real UI, in independent sessions. 730 kg ordered, 725 kg received,
// 705 kg accepted and 20 kg rejected; 705 kg delivered and confirmed by the buyer in their own account. The order is
// reconciled but never shown as 730 kg delivered or as completed; a procurement manager closes it with the
// documented 25 kg variance, which every later session still sees.
// WP5: each role's order page offers only what that role may do (M1), the Fulfilment Center lists the work across
// orders, the buyer follows the order in their portal and downloads the delivery record (M2), and the supplier request
// shows as not sent because no consent to be contacted was recorded (M3).
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

// Physical events are recorded as already happened: the API refuses receipts and deliveries in the future.
const hoursAgo = (hours: number) => {
  const at = new Date(Date.now() - hours * 3_600_000);
  return new Date(at.getTime() - at.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
const figure = (page: Page, label: string) => page.getByLabel('Fulfilment quantities').locator(`dd[data-fulfilment-figure="${label}"]`);

test.describe.serial('WP4 fulfilment, buyer confirmation and close-out', () => {
  const farmer = `Marcia Campbell ${run}`;
  const site = `Linstead Packhouse ${run}`;
  const reference = `PL-${run}`;
  let orderPath = '';

  test('a 730 kg order is committed through the supplier’s recorded decision', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/suppliers');
    await expect(page.getByText('Loading…')).toHaveCount(0);
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
    await expect(page.getByText('Loading…')).toHaveCount(0);
    const add = page.getByRole('form', { name: 'Add a site' });
    await add.getByLabel('Name').fill(site);
    await add.getByLabel('Type').fill('packhouse');
    await add.getByLabel('Parish').fill('St. Catherine');
    await add.getByRole('button', { name: 'Add site' }).click();
    await expect(page.getByRole('list', { name: 'Fulfilment sites' })).toContainText(site);

    await page.goto('/orders/new');
    await expect(page.getByText('Loading…')).toHaveCount(0);
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
    await receipt.getByLabel('Received at').fill(hoursAgo(3));
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
    // The departure time is stated (entered afterwards, an hour ago); the system keeps its own recording time beside it.
    const dispatch = page.getByRole('form', { name: `Dispatch ${reference}` });
    await dispatch.getByLabel('Time the goods left').fill(hoursAgo(1));
    await dispatch.getByRole('button', { name: 'Record dispatch' }).click();
    await expect(shipment).toHaveAttribute('data-shipment', 'DISPATCHED');
    await expect(shipment).toContainText('(stated; recorded');
    await shipment.getByRole('button', { name: 'Record delivery' }).click();
    const delivery = page.getByRole('form', { name: `Delivery for ${reference}` });
    await delivery.getByLabel('Delivered (kg)').fill('705');
    await delivery.getByLabel('Delivered at').fill(hoursAgo(0));
    await delivery.getByRole('button', { name: 'Save delivery' }).click();
    await expect(figure(page, 'Delivered')).toHaveText('705 kg');
    await expect(figure(page, 'Buyer-confirmed')).toHaveText('0 kg');
    await expect(shipment).toContainText('Not confirmed by the buyer');
    // WP5 M1: a warehouse operator records physical facts only; commercial controls are not offered at all.
    await expect(shipment.getByRole('button', { name: "Record buyer's confirmation" })).toHaveCount(0);
    await expect(page.getByRole('form', { name: 'Reconcile' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Close the order' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Supply' }).getByRole('button', { name: 'Propose supply' })).toHaveCount(0);
    // Sections the role cannot read are absent, not refusals (technical-debt item 20).
    await expect(page.getByRole('heading', { name: 'Needs attention' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Recovery' })).toHaveCount(0);
    // (Next.js keeps an empty route-announcer alert on every page; only refusal messages matter here.)
    await expect(page.getByRole('alert').filter({ hasText: /permission|access|denied|forbidden|not allowed/i })).toHaveCount(0);
    await page.goto('/fulfilment');
    const awaiting = page.locator('[data-queue="awaiting_buyer_confirmation"]');
    await expect(awaiting).toContainText(`Shipment ${reference}`);
    await expect(awaiting).toHaveAttribute('data-actionable', 'no');
    await page.screenshot({ path: `${shots}/19b-fulfilment-center-warehouse.png`, fullPage: true });
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
    // A coordinator cannot accept a variance (the server refuses it: test_fulfilment_accounting). WP5 M1: the form is
    // not offered; the page says who can close with a documented difference.
    await expect(page.getByRole('form', { name: 'Close with an accepted variance' })).toHaveCount(0);
    await expect(page.locator('[data-variance-needs-manager]')).toContainText('procurement manager');
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
    // Nothing is left asking for action on an ended order.
    await expect(manager.page.getByRole('region', { name: 'Needs attention' })).toContainText('No open supply exceptions for this order.');
    await expect(manager.page.getByRole('region', { name: 'Supply' })).toContainText('Order ended');
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

  test('an auditor sees every record, changes nothing and can flag an issue', async ({ browser }) => {
    const { context, page } = await freshSession(browser, users.auditor_a);
    await page.goto(orderPath);
    await expect(figure(page, 'Delivered')).toHaveText('705 kg');
    await expect(page.locator('[data-read-only-fulfilment]')).toContainText('does not change them');
    await expect(page.getByText('Record a receipt')).toHaveCount(0);
    await expect(page.getByRole('form', { name: 'Reconcile' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Raise a discrepancy' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Close the order' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Edit terms' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Flag for audit' }).click();
    const flag = page.getByRole('form', { name: 'Flag for audit' });
    await flag.getByLabel('Subject').fill('Rejected quantity');
    await flag.getByLabel('What should be looked at?').fill('Check the grading evidence for the 20 kg rejected');
    await flag.getByRole('button', { name: 'Record flag' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Flag recorded' })).toBeVisible();
    await expect(figure(page, 'Accepted')).toHaveText('705 kg');
    await context.close();
  });

  test('the buyer follows the order in their portal and downloads the delivery record', async ({ browser }) => {
    const { context, page } = await freshSession(browser, users.buyer_a);
    await page.goto('/');
    await page.waitForURL(url => url.pathname === '/buyer');
    await page.getByRole('list', { name: 'My orders' }).getByRole('button', { name: /Plantain, grade A/ }).first().click();
    const order = page.getByRole('region', { name: /Order Plantain, grade A/ });
    await expect(order.locator('[data-buyer-figure="delivered_kg"]')).toHaveText('705 kg');
    await expect(order.locator('[data-buyer-figure="confirmed_by_you_kg"]')).toHaveText('705 kg');
    await expect(order.locator('[data-buyer-figure="relayed_by_staff_kg"]')).toHaveText('0 kg');
    await expect(order.locator('[data-buyer-figure="still_to_deliver_kg"]')).toHaveText('25 kg');
    await expect(order.locator('[data-statement-source="BUYER_ACCOUNT"]')).toContainText('Confirmed by the buyer in their account');
    await expect(order).not.toContainText(farmer); // supplier identities stay with staff
    const download = page.waitForEvent('download');
    await order.getByRole('button', { name: 'Download delivery record (CSV)' }).click();
    const file = await download;
    const text = readFileSync(await file.path(), 'utf8');
    expect(text.split('\r\n')[0]).toContain('shipment_reference');
    expect(text).toContain(reference);
    expect(text).toContain('Confirmed by the buyer in their account');
    await page.screenshot({ path: `${shots}/23-buyer-portal.png`, fullPage: true });
    await context.close();
  });

  test('the supplier request shows as not sent because no consent to be contacted was recorded', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/notifications');
    const messages = page.getByRole('list', { name: 'Outbound messages' });
    await expect(messages.locator('[data-notification-status="BLOCKED_NO_CONSENT"]').filter({ hasText: farmer }).first()).toContainText('Not sent: no consent');
    await expect(page.locator('[data-notification-provider]')).toContainText('nothing is sent');
  });

  test('another organization sees none of it', async ({ browser }) => {
    const outsider = await freshSession(browser, users.coordinator_b);
    await outsider.page.goto(orderPath);
    await expect(outsider.page.getByRole('alert')).toBeVisible();
    await expect(outsider.page.getByText(farmer)).toHaveCount(0);
    await outsider.context.close();
  });
});
