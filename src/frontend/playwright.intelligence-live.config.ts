import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-live', timeout:30_000, workers:1,
  use:{ baseURL:'http://127.0.0.1:3000', viewport:{width:1440,height:1000}, trace:'retain-on-failure' },
  outputDir:'artifacts/final-live-results', reporter:[['list']],
});
