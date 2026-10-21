import { expect, test } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`national intelligence works at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.setViewportSize({ width, height:900 });
    await page.goto('/intelligence-lab');
    await expect(page.getByRole('heading', { name:'Intelligence Lab', exact:true })).toBeVisible();
    await expect(page.getByText('2026 Q1: 4,069 tonnes')).toBeVisible();
    await expect(page.getByText('39 / 40 production records')).toBeVisible();
    await expect(page.getByRole('heading',{name:'Lettuce and chicory',exact:true})).toBeVisible();
    await expect(page.getByText(/1,496 annual production and harvested-area observations/)).toBeVisible();
    await expect(page.getByText('Quarantined: 2016 Q3 production')).toBeVisible();
    await page.getByText('Accessible historical observation table', {exact:true}).click();
    await expect(page.getByRole('cell', {name:'Unavailable',exact:true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    await page.evaluate(() => window.scrollTo(0,0));
    await page.screenshot({path:`artifacts/screenshots/intelligence-${width}.png`,fullPage:true});
    expect(errors).toEqual([]);
  });
}

test('missing official snapshot shows an error and retry recovers', async ({ page }) => {
  for (const source of ['**/agriculture/intelligence.json', '**/agricultural-intelligence']) {
    await page.route(source, route => route.fulfill({ status:503, body:'unavailable' }));
  }
  await page.goto('/intelligence-lab');
  await expect(page.getByRole('heading', {name:'Agricultural intelligence unavailable',exact:true})).toBeVisible();
  await expect(page.getByText('2026 Q1: 0 tonnes')).toHaveCount(0);
  for (const source of ['**/agriculture/intelligence.json', '**/agricultural-intelligence']) await page.unroute(source);
  await page.getByRole('button', {name:'Retry data request'}).click();
  await expect(page.getByText('2026 Q1: 4,069 tonnes')).toBeVisible();
});

test('incomplete snapshot fails safely without a render crash', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const source of ['**/agriculture/intelligence.json', '**/agricultural-intelligence']) {
    await page.route(source, route => route.fulfill({ json: { schema_version:1, series:[] } }));
  }
  await page.goto('/intelligence-lab');
  await expect(page.getByRole('heading', {name:'Agricultural intelligence unavailable',exact:true})).toBeVisible();
  await expect(page.getByText(/artifact is incomplete or invalid/)).toBeVisible();
  expect(errors).toEqual([]);
});
