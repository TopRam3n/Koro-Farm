import { expect, test } from '@playwright/test';

const screenshots = 'artifacts/screenshots';
const requirementPath = '/requirements/00000000-0000-0000-0000-000000000500';

test('real 500kg / 80kg competition flow', async ({ page, browser }) => {
  const startedAt = Date.now();
  const consoleErrors: string[] = [];
  const consoleWarnings: string[] = [];
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('console', message => { if (message.type() === 'warning') consoleWarnings.push(message.text()); });
  page.on('pageerror', error => consoleErrors.push(error.message));
  await page.goto(requirementPath);
  const demoMode = await page.locator('[data-app-mode="demo"]').count() > 0;
  await expect(page.getByTestId('committed-kg')).toContainText('500');
  await expect(page.getByTestId('standby-kg')).toContainText('100');
  await expect(page.getByText('Supply commitment covered.')).toBeVisible();
  await page.screenshot({ path: `${screenshots}/01-initial.png`, fullPage: true });
  await page.reload();
  await expect(page.getByTestId('committed-kg')).toContainText('500');

  await page.getByRole('button', { name: /Simulate 80/ }).click();
  await expect(page.getByTestId('committed-kg')).toContainText('420');
  await expect(page.getByTestId('shortfall-kg')).toContainText('80 kg');
  await expect(page.getByTestId('supply-health')).toContainText('AT RISK');
  await page.screenshot({ path: `${screenshots}/02-dropout.png`, fullPage: true });
  await page.screenshot({ path: `${screenshots}/03-at-risk.png`, fullPage: true });

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  await secondPage.goto(requirementPath);
  if (!demoMode) {
    await expect(secondPage.getByTestId('committed-kg')).toContainText('420');
    await page.reload();
    await expect(page.getByTestId('committed-kg')).toContainText('420');
  }

  await page.getByRole('button', { name: /Run recovery plan/ }).click();
  await expect(page.getByText('Committed coverage restored')).toBeVisible();
  await expect(page.getByTestId('committed-kg')).toContainText('500');
  await expect(page.getByText('Supply commitment covered.')).toBeVisible();
  await expect(page.getByText('allocation lost', { exact: true }).last()).toBeVisible();
  if (!demoMode) {
    await expect(page.getByText('requirement at_risk')).toBeVisible();
    await expect(page.getByText('recovery started')).toBeVisible();
    await expect(page.getByText('allocation standby_activated')).toHaveCount(2);
  }
  await expect(page.getByText('recovery completed')).toBeVisible();
  await page.screenshot({ path: `${screenshots}/04-recovery.png`, fullPage: true });
  await page.screenshot({ path: `${screenshots}/05-restored.png`, fullPage: true });
  if (!demoMode) {
    await page.reload();
    await expect(page.getByText('Committed coverage restored')).toBeVisible();
    await secondPage.reload();
    await expect(secondPage.getByTestId('committed-kg')).toContainText('500');
    await expect(secondPage.getByTestId('supply-health')).toContainText('COVERED');
  }
  await secondContext.close();
  await expect(page.getByText(/500\s*kg delivered|order fulfilled|guaranteed delivery/i)).toHaveCount(0);
  await expect(page.getByText(/probability/i)).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
  expect(consoleWarnings).toEqual([]);
  await test.info().attach('demo-timing', { body: `${Date.now() - startedAt}ms`, contentType: 'text/plain' });
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }]) {
  test(`core dashboard fits ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(requirementPath);
    await expect(page.getByRole('heading', { name: 'Committed supply by parish' })).toBeVisible();
    for (const label of ['Required commitment', 'Standby', 'Physical fulfilment', 'Recovery & agent activity', 'Risk:', 'Recovery cost snapshot']) {
      const element = page.getByText(label, { exact: false }).first();
      await expect(element).toBeVisible();
      const box = await element.boundingBox();
      expect(box, `${label} should have a layout box`).not.toBeNull();
      expect(box!.x, `${label} should not overflow left`).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width, `${label} should not overflow right`).toBeLessThanOrEqual(viewport.width);
    }
    const overflows = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflows).toBe(false);
    await page.screenshot({ path: `${screenshots}/viewport-${viewport.width}x${viewport.height}.png`, fullPage: true });
  });
}
