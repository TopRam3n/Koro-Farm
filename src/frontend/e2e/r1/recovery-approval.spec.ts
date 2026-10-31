import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// WP3: a capacity cut is detected by the worker, the recovery agent proposes, a coordinator approves the exact
// proposal in Needs attention, the gateway applies it, and a new supplier's acceptance completes recovery.
// Requires the worker (python -m src.backend.app.worker), which also runs the recovery agent; see README.md.
type TestUser = { key: string; email: string; password: string };
const usersFile = process.env.R1_E2E_USERS;
const users: Record<string, TestUser> = usersFile
  ? Object.fromEntries((JSON.parse(readFileSync(usersFile, 'utf8')).users as TestUser[]).map(u => [u.key, u]))
  : {};
const run = Date.now().toString(36).slice(-5).toUpperCase();
const shots = 'artifacts/r1-e2e-screens';
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

const figure = (page: Page, label: string) => page.locator(`dd[data-figure="${label}"]`);

test.describe.serial('WP3 recovery with human approval', () => {
  const buyerName = `Montego Bay Yam Exporters ${run}`;
  const ena = `Ena Gordon ${run}`;
  const paul = `Paul Reid ${run}`;
  let orderPath = '';

  test('an order is committed with authorized standby, through recorded supplier decisions', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/buyers');
    await page.getByLabel('Buyer name').fill(buyerName);
    await page.getByLabel('Buyer type').fill('Exporter');
    await page.getByLabel('Delivery destination').fill('Port of Montego Bay');
    await page.getByRole('button', { name: 'Add buyer' }).click();
    await expect(page.getByRole('status')).toHaveText(`Saved ${buyerName}.`);

    await page.goto('/suppliers');
    for (const [name, parish] of [[ena, 'Manchester'], [paul, 'Clarendon']]) {
      await page.getByLabel('Farmer name').fill(name);
      await page.getByLabel('Parish').fill(parish);
      await page.getByRole('button', { name: 'Add supplier' }).click();
      await expect(page.getByRole('status')).toHaveText(`Saved supplier ${name}.`);
    }
    for (const [name, parish] of [[ena, 'Manchester'], [paul, 'Clarendon']]) {
      await page.getByRole('combobox', { name: 'Supplier', exact: true }).selectOption({ label: `${name} (${parish})` });
      await page.getByLabel('Crop').selectOption({ label: 'Yam' });
      await page.getByLabel('Expected grade').selectOption('A');
      await page.getByLabel('Harvest from').fill('2026-11-20');
      await page.getByLabel('Harvest to').fill('2026-12-10');
      await page.getByLabel('Expected harvest (kg)').fill('400');
      await page.getByLabel('Available now (kg)').fill('300');
      await page.getByLabel('Farmgate price (J$/kg)').fill('600');
      await page.getByLabel('How you received this').fill('farm visit');
      await page.getByLabel('Attestation').fill('signed declaration form');
      await page.getByRole('button', { name: 'Record lot' }).click();
      await expect(page.getByRole('status')).toContainText(`for ${name} as declared`);
    }

    await page.goto('/orders/new');
    await page.getByLabel('Buyer').selectOption({ label: buyerName });
    await page.getByLabel('Crop').selectOption({ label: 'Yam' });
    await page.getByLabel('Grade').selectOption('A');
    await page.getByLabel('Required quantity (kg)').fill('300');
    await page.getByLabel('Delivery from').fill('2026-12-01');
    await page.getByLabel('Delivery to').fill('2026-12-12');
    await page.getByRole('button', { name: 'Create order' }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    orderPath = new URL(page.url()).pathname;

    await page.getByRole('region', { name: 'Supply' }).getByRole('button', { name: 'Propose supply' }).click();
    const table = page.getByRole('table', { name: 'Supplier allocations' });
    for (const [label, standby] of [[`${ena} commitment`, false], [`${paul} standby`, true]] as const) {
      await table.getByRole('button', { name: `Ask ${label}`, exact: true }).click();
      await table.getByRole('button', { name: `Record response for ${label}`, exact: true }).click();
      const form = page.getByRole('form', { name: `Supplier response for ${label.split(' ').slice(0, 3).join(' ')}` });
      await form.getByLabel('How the supplier told you').fill('phone call with farmer');
      if (standby) await form.getByLabel('Activation conditions').fill('Only to replace supply another farmer cannot deliver');
      await form.getByRole('button', { name: 'Save supplier response' }).click();
      await expect(form).toHaveCount(0);
    }
    await expect(figure(page, 'Committed')).toHaveText('300 kg');
    await expect(figure(page, 'Authorized standby')).toHaveText('60 kg');
  });

  test('a capacity cut produces a proposal, and nothing changes until a person approves it', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/suppliers');
    const relay = page.getByRole('form', { name: 'Relay capacity report' });
    await relay.getByLabel('Lot').selectOption({ label: `${ena} · YAM · 2026-11-20` });
    await relay.getByLabel('Farmer can still supply (kg)').fill('190');
    await relay.getByLabel('How the farmer told you').fill('phone call with farmer');
    await relay.getByLabel('How it was attested').fill('verbal');
    await relay.getByRole('button').click();
    await expect(page.getByRole('status')).toContainText('capacity report of 190 kg');

    await page.goto('/exceptions');
    const task = page.locator('[data-recovery-task]').filter({ hasText: buyerName });
    const proposal = task.getByRole('region', { name: 'Recovery proposal 1' });
    await expect(proposal).toBeVisible(LIVE);
    await expect(task).toContainText('Awaiting approval');
    const actions = proposal.getByRole('list', { name: 'Proposed actions' });
    await expect(actions).toContainText(`${ena} can no longer supply 110 kg`);
    await expect(actions).toContainText(`Activate 60 kg of standby that ${paul}`);
    await expect(actions).toContainText(`Ask ${paul} (Clarendon) for 50 kg`);
    await expect(proposal).toContainText('Coordinator approval');
    await expect(proposal).toContainText('Draft update for the buyer (not sent)');
    await page.screenshot({ path: `${shots}/13-recovery-proposal-awaiting-approval.png`, fullPage: true });

    // Waiting is not approval: the order is unchanged.
    await page.goto(orderPath);
    await expect(figure(page, 'Exposed')).toHaveText('110 kg');
    await expect(figure(page, 'Authorized standby')).toHaveText('60 kg');
    await expect(page.getByRole('region', { name: 'Recovery', exact: true })).toContainText('Awaiting approval');
  });

  test('another organization sees none of it', async ({ browser }) => {
    const outsider = await freshSession(browser, users.coordinator_b);
    await outsider.page.goto('/exceptions');
    await expect(outsider.page.getByText('No recovery in progress.')).toBeVisible();
    await expect(outsider.page.getByText(buyerName)).toHaveCount(0);
    await outsider.context.close();
  });

  test('the coordinator approves the exact proposal; the gateway applies it and the new supplier completes it', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto('/exceptions');
    const task = page.locator('[data-recovery-task]').filter({ hasText: buyerName });
    await task.getByRole('button', { name: 'Approve proposal' }).click();
    await expect(task).toContainText('Waiting for suppliers', LIVE);
    await expect(task.getByText('Applied')).toHaveCount(3, LIVE);

    await page.goto(orderPath);
    await expect(figure(page, 'Exposed')).toHaveText('0 kg', LIVE);
    await expect(figure(page, 'Committed')).toHaveText('250 kg');
    await expect(figure(page, 'Awaiting supplier')).toHaveText('50 kg');
    await expect(page.getByRole('region', { name: 'Needs attention' })).toContainText('No open supply exceptions for this order.', LIVE);
    await page.screenshot({ path: `${shots}/14-recovery-applied-awaiting-supplier.png`, fullPage: true });

    // Only the supplier's recorded acceptance turns the request into supply.
    const table = page.getByRole('table', { name: 'Supplier allocations' });
    await table.getByRole('button', { name: `Record response for ${paul} commitment`, exact: true }).click();
    const form = page.getByRole('form', { name: `Supplier response for ${paul}` });
    await form.getByLabel('How the supplier told you').fill('phone call with farmer');
    await form.getByRole('button', { name: 'Save supplier response' }).click();
    await expect(figure(page, 'Committed')).toHaveText('300 kg', LIVE);
    const recovery = page.getByRole('region', { name: 'Recovery', exact: true });
    await expect(recovery.locator('[data-recovery-task="COMPLETED"]')).toBeVisible(LIVE);
    const timeline = recovery.getByRole('list', { name: 'Recovery timeline' });
    await expect(timeline).toContainText('approved by supply coordinator');
    await expect(timeline).toContainText('Alpha Coordinator');
    await expect(timeline).toContainText('Recovery gateway');
    await expect(page.getByRole('list', { name: 'Order history' })).toContainText('Recovery approved', LIVE);
    await page.screenshot({ path: `${shots}/15-recovery-completed-with-timeline.png`, fullPage: true });
  });
});
