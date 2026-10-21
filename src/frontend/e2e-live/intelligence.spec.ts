import { expect, test } from '@playwright/test';

// Prepared local verification only; not part of the default demo suite.
// Requires a frontend compiled for live API_URL http://127.0.0.1:8000 and the
// existing explicit synthetic demo authentication on both local processes.
// This setup does not certify real Supabase login. Starting that configuration
// was blocked by automatic approval review in the October 18 run; tests unrun.

test('Intelligence Lab reads the real backend and renders its saved experiment', async ({ page }) => {
  const errors: string[] = [];
  const requests: {url:string;method:string}[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if(message.type()==='error') errors.push(message.text()); });
  page.on('request', request => requests.push({url:request.url(),method:request.method()}));
  const responsePromise = page.waitForResponse(response => response.url() === 'http://127.0.0.1:8000/agricultural-intelligence');
  await page.goto('/intelligence-lab');
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.quality.validated_counts.production).toBe(39);
  expect(body.experiment.metrics.holdout.ridge_lags.mae_tonnes).toBeCloseTo(553.782226,5);
  expect(body.annual_context.validation.observations).toBe(1496);
  await expect(page.getByText('2026 Q1: 4,069 tonnes')).toBeVisible();
  await expect(page.getByText(/not an untouched independent holdout/)).toBeVisible();
  await expect(page.getByText('Validated offline artifact served by the authenticated API',{exact:false})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Lettuce and chicory',exact:true})).toBeVisible();
  expect(requests.some(r=>r.url.includes('/agriculture/intelligence.json'))).toBe(false);
  expect(requests.filter(r=>r.url.startsWith('http://127.0.0.1:8000')).every(r=>r.method==='GET')).toBe(true);
  expect(errors).toEqual([]);
  await page.screenshot({path:'artifacts/screenshots/final-live-intelligence-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth)).toBe(false);
  await page.screenshot({path:'artifacts/screenshots/final-live-intelligence-mobile.png',fullPage:true});
});

test('live API failure remains visible without substituting cached demo data', async ({page}) => {
  const cached: string[]=[];
  page.on('request',r=>{if(r.url().includes('/agriculture/intelligence.json'))cached.push(r.url());});
  await page.route('http://127.0.0.1:8000/agricultural-intelligence',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Verification: offline artifact unavailable'})}));
  await page.goto('/intelligence-lab');
  await expect(page.getByRole('heading',{name:'Agricultural intelligence unavailable',exact:true})).toBeVisible();
  await expect(page.getByText('2026 Q1: 4,069 tonnes')).toHaveCount(0);
  expect(cached).toEqual([]);
  await page.unroute('http://127.0.0.1:8000/agricultural-intelligence');
  await page.getByRole('button',{name:'Retry data request'}).click();
  await expect(page.getByText('2026 Q1: 4,069 tonnes')).toBeVisible();
});
