import { expect, test } from '@playwright/test';

const routes = [
  ['/', 'Supply Assurance Control Room'],
  ['/programmes', 'Programmes'],
  ['/demand', 'Demand'],
  ['/supply', 'Supply Network'],
  ['/assurance', 'Assurance Center'],
  ['/scenario-lab', 'KoroFarm Scenario Lab'],
  ['/fulfilment', 'Fulfilment Center'],
  ['/network', 'Network Intelligence'],
  ['/compliance', 'Compliance Registry'],
  ['/traceability', 'Traceability Explorer'],
  ['/trade-evidence', 'Trade Evidence'],
  ['/analytics', 'Analytics'],
  ['/agent-operations', 'Agent Operations'],
  ['/activity', 'Activity & Audit'],
  ['/integrations', 'Integrations'],
  ['/settings', 'Settings'],
] as const;

test('enterprise workspace route map is navigable and honest', async ({ page }) => {
  for (const [route, heading] of routes) {
    await page.goto(route);
    await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.locator('body')).not.toContainText(/guaranteed delivery|credit score/i);
  }
  await page.goto('/');
  await page.screenshot({ path: 'artifacts/screenshots/command-center.png', fullPage: true });
});

test('command palette supports keyboard navigation discovery', async ({ page }) => {
  await page.goto('/');
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
  await page.goto('/scenario-lab');
  await expect(page.getByText('SIMULATION', { exact: true })).toBeVisible();
  await expect(page.getByText('No live writes')).toBeVisible();
  await page.getByLabel('Quantity impact').fill('140');
  await expect(page.getByText('140 kg', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('80 kg', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'artifacts/screenshots/scenario-lab.png', fullPage: true });
});
