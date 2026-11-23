import { defineConfig, devices } from '@playwright/test';

// R1 browser E2E against a live stack: production Next.js build, FastAPI backend, disposable PostgreSQL,
// and the test-only auth stand-in (e2e/r1/support/auth-stub.mjs). See e2e/r1/README.md for how to run it.
export default defineConfig({
  testDir: './e2e/r1',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.R1_BASE_URL ?? 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  reporter: [['list'], ['html', { outputFolder: 'artifacts/r1-e2e-report', open: 'never' }]],
  outputDir: 'artifacts/r1-e2e-results',
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
});
