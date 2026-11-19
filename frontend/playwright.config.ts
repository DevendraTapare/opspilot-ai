import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 180000,
  expect: { timeout: 30000 },
  outputDir: process.env.OPSPILOT_BROWSER_TEST_OUTPUT || 'test-results',
  reporter: [['list'], ['json', { outputFile: `${process.env.OPSPILOT_BROWSER_TEST_OUTPUT || 'test-results'}/stage6-results.json` }]],
  use: { baseURL: 'http://127.0.0.1:3001', browserName: 'chromium',
    viewport: { width: 1440, height: 1000 }, trace: 'off', screenshot: 'only-on-failure' },
});
