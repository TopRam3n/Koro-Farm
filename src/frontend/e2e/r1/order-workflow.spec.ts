import { readFileSync } from 'node:fs';
import { type Browser, type Page, expect, test } from '@playwright/test';

// Users are created by src/backend/scripts/seed_e2e.py; the path is passed in R1_E2E_USERS.
type TestUser = { key: string; email: string; password: string; organization_name: string };
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

const figure = (page: Page, label: string) => page.locator(`dd[data-figure="${label}"]`);

test.describe.serial('R1 order workflow through the real UI', () => {
  let orderPath = '';
  const buyerName = `Caribbean Sauce Co. ${run}`;
  const farmers = [`Marcia Ellis ${run}`, `Devon Brown ${run}`];

  test('a coordinator creates a buyer, suppliers, declared lots and an unfamiliar order', async ({ page }) => {
    await signIn(page, users.coordinator_a);

    await page.goto('/buyers');
    await page.getByLabel('Buyer name').fill(buyerName);
    await page.getByLabel('Buyer type').fill('Processor');
    await page.getByLabel('Delivery destination').fill('Kingston processing plant');
    await page.getByRole('button', { name: 'Add buyer' }).click();
    await expect(page.getByRole('status')).toHaveText(`Saved ${buyerName}.`);
    await expect(page.getByRole('list', { name: 'Buyers' })).toContainText(buyerName);

    await page.goto('/suppliers');
    for (const [name, parish] of [[farmers[0], 'St. Elizabeth'], [farmers[1], 'Manchester']]) {
      await page.getByLabel('Farmer name').fill(name);
      await page.getByLabel('Parish').fill(parish);
      await page.getByRole('button', { name: 'Add supplier' }).click();
      await expect(page.getByRole('list', { name: 'Suppliers' })).toContainText(name);
    }
    for (const [name, expected, available] of [[farmers[0], '500', '450'], [farmers[1], '400', '400']]) {
      await page.getByRole('combobox', { name: 'Supplier', exact: true }).selectOption({ label: `${name} (${name === farmers[0] ? 'St. Elizabeth' : 'Manchester'})` });
      await page.getByLabel('Crop').selectOption({ label: 'Scotch bonnet pepper' });
      await page.getByLabel('Expected grade').selectOption('A');
      await page.getByLabel('Harvest from').fill('2026-11-20');
      await page.getByLabel('Harvest to').fill('2026-12-10');
      await page.getByLabel('Expected harvest (kg)').fill(expected);
      await page.getByLabel('Available now (kg)').fill(available);
      await page.getByLabel('Farmgate price (J$/kg)').fill('620');
      await page.getByLabel('How you received this').fill('phone call with farmer');
      await page.getByLabel('Attestation').fill('verbal');
      await page.getByRole('button', { name: 'Record lot' }).click();
      await expect(page.getByRole('status')).toContainText(`for ${name} as declared`);
    }
    const lots = page.getByRole('table', { name: 'Production lots' });
    await expect(lots.getByRole('row', { name: new RegExp(farmers[0]) })).toContainText('Declared');
    await page.screenshot({ path: `${shots}/01-suppliers-and-declared-lots.png`, fullPage: true });

    await page.goto('/orders/new');
    await page.getByLabel('Buyer').selectOption({ label: buyerName });
    await page.getByLabel('Crop').selectOption({ label: 'Scotch bonnet pepper' });
    await page.getByLabel('Grade').selectOption('A');
    await page.getByLabel('Required quantity (kg)').fill('730');
    await page.getByLabel('Delivery from').fill('2026-12-01');
    await page.getByLabel('Delivery to').fill('2026-12-12');
    await page.getByLabel('Product form').fill('Fresh, whole');
    await page.getByLabel('Destination').fill('Kingston processing plant');
    await page.getByLabel('Currency').fill('JMD');
    await page.getByRole('button', { name: 'Create order' }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    orderPath = new URL(page.url()).pathname;

    // Persisted: a full reload reads it back from the API.
    await page.reload();
    const terms = page.getByRole('region', { name: 'Order terms' });
    await expect(terms).toContainText('730 kg');
    await expect(terms).toContainText(buyerName);
    await expect(terms).toContainText('SCOTCH BONNET · Grade A');
    await expect(terms).toContainText('Version 1');
  });

  test('edits are versioned and supply goes proposed -> awaiting supplier -> committed only with a recorded response', async ({ page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    const terms = page.getByRole('region', { name: 'Order terms' });
    await terms.getByRole('button', { name: 'Edit terms' }).click();
    await page.getByLabel('Notes').fill('Volume confirmed by buyer email');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(terms).toContainText('Version 2');
    await expect(terms).toContainText('Volume confirmed by buyer email');

    const supply = page.getByRole('region', { name: 'Supply' });
    await expect(figure(page, 'Committed')).toHaveText('0 kg');
    await supply.getByRole('button', { name: 'Propose supply' }).click();
    const allocations = page.getByRole('table', { name: 'Supplier allocations' });
    await expect(allocations).toBeVisible();
    await expect(allocations).toContainText('Proposed');
    await expect(figure(page, 'Committed')).toHaveText('0 kg');  // a proposal is not a commitment
    await expect(supply).toContainText('Assembling supply');
    await page.screenshot({ path: `${shots}/02-proposed-not-committed.png`, fullPage: true });

    const ask = allocations.getByRole('button', { name: /^Ask .+ commitment$/ }).first();
    const askedLabel = (await ask.getAttribute('aria-label'))!;
    const who = askedLabel.replace(/^Ask /, '').replace(/ commitment$/, '');
    await ask.click();
    const row = allocations.getByRole('row', { name: new RegExp(who) }).first();
    await expect(row).toContainText('Awaiting supplier');
    await expect(figure(page, 'Committed')).toHaveText('0 kg');  // asking is not agreement

    await allocations.getByRole('button', { name: `Record response for ${who} commitment` }).click();
    const response = page.getByRole('form', { name: `Supplier response for ${who}` });
    await response.getByLabel('How the supplier told you').fill('phone call with farmer');
    await response.getByLabel('Evidence reference').fill(`call log ${run}`);
    await response.getByRole('button', { name: 'Save supplier response' }).click();
    await expect(row).toContainText('Committed');
    await expect(figure(page, 'Committed')).not.toHaveText('0 kg');

    const history = page.getByRole('list', { name: 'Order history' });
    for (const entry of ['Requirement created', 'Requirement updated', 'Plan proposed', 'Solicitation sent', 'Supplier accepted']) {
      await expect(history).toContainText(entry);
    }
    await page.screenshot({ path: `${shots}/03-committed-after-recorded-response.png`, fullPage: true });
  });

  test('a second authenticated session in the same organization sees the same persisted state', async ({ browser, page }) => {
    await signIn(page, users.coordinator_a);
    await page.goto(orderPath);
    const committed = await figure(page, 'Committed').textContent();
    const version = (await page.getByRole('region', { name: 'Order terms' }).textContent())!.match(/Version \d+/)![0];

    const colleague = await freshSession(browser, users.colleague_a);
    await colleague.page.goto('/orders');
    await expect(colleague.page.getByRole('table', { name: 'Orders' })).toContainText(buyerName);
    await colleague.page.goto(orderPath);
    await expect(figure(colleague.page, 'Committed')).toHaveText(committed!);
    await expect(colleague.page.getByRole('region', { name: 'Order terms' })).toContainText(version);
    await expect(colleague.page.getByRole('list', { name: 'Order history' })).toContainText('Supplier accepted');
    await colleague.page.screenshot({ path: `${shots}/04-colleague-session.png`, fullPage: true });
    await colleague.context.close();
  });

  test('another organization sees none of it and cannot open it by URL', async ({ browser }) => {
    const outsider = await freshSession(browser, users.coordinator_b);
    await outsider.page.goto('/orders');
    await expect(outsider.page.getByText('No orders yet')).toBeVisible();
    await outsider.page.goto('/buyers');
    await expect(outsider.page.getByText('No buyers yet')).toBeVisible();
    await outsider.page.goto('/suppliers');
    await expect(outsider.page.getByText('No suppliers yet')).toBeVisible();
    await outsider.page.goto(orderPath);
    // Next.js renders its own empty role="alert" route announcer; target the error the API returned.
    await expect(outsider.page.getByRole('alert').filter({ hasText: 'requirement not found' })).toBeVisible();
    await expect(outsider.page.getByText(buyerName)).toHaveCount(0);
    await outsider.page.screenshot({ path: `${shots}/05-other-organization-blocked.png`, fullPage: true });
    await outsider.context.close();
  });
});
