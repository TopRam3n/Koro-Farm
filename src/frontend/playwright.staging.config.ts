import { defineConfig, devices } from '@playwright/test';

// Staging release gate for real Supabase authentication (e2e/staging). Not part of `npm run test:e2e` and
// not run in CI. See docs/product/STAGING_AUTH_VERIFICATION.md.
export default defineConfig({
  testDir: './e2e/staging',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.STAGING_BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  reporter: [['list'], ['html', { outputFolder: 'artifacts/staging-auth-report', open: 'never' }]],
  outputDir: 'artifacts/staging-auth-results',
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
});
