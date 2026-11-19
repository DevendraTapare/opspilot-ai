import { test, expect, type Page } from '@playwright/test';

const HUMAN = process.env.OPSPILOT_BROWSER_TEST_HUMAN || 'stage6-synthetic-browser-human-' + 'h'.repeat(40);
const KEY = process.env.OPSPILOT_BROWSER_TEST_KEY || 'stage6-bff-test-key-' + 'k'.repeat(40);
const OUTPUT = process.env.OPSPILOT_BROWSER_TEST_OUTPUT || 'test-results';
const ORIGIN = 'http://127.0.0.1:3001';

test('release capture: measured healthy baseline', async ({ page }) => {
  test.skip(process.env.OPSPILOT_BROWSER_TEST_BASELINE !== '1', 'Release baseline is explicitly enabled by its isolated launcher');
  await page.goto('/');
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible();
  await expect.poll(async () => {
    const data = await (await page.request.get('/api/ops/overview')).json();
    return data.services.length === 3 && data.services.every((s: { status: string }) => s.status === 'healthy');
  }).toBeTruthy();
  await expect(page.getByText('checkout-service', { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: `${OUTPUT}/healthy.png`, fullPage: true });
});

async function login(page: Page) {
  await page.goto('/');
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign in as operator' }).click();
  await page.getByLabel('Operator credential').fill(HUMAN);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('synthetic-browser-human', { exact: true })).toBeVisible();
}

async function incidentAndRun(page: Page, budget = '180') {
  await page.getByRole('button', { name: 'Simulate incident' }).click();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Start incident', exact: true }).click();
  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]{36}$/, { timeout: 90000 });
  const incidentId = page.url().split('/').at(-1)!;
  await page.getByRole('button', { name: 'Launch investigation' }).click();
  await expect(page.getByLabel('Execution mode')).toHaveValue('fixture');
  await page.getByLabel('Time budget (seconds)').fill(budget);
  await page.getByRole('button', { name: 'Start investigation', exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/[0-9a-f-]{36}$/);
  const runId = page.url().split('/').at(-1)!;
  return { runId, incidentId };
}

test('real browser: investigate, approve exact action, execute once, verify recovery and audit', async ({ page, request }, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const forbidden: string[] = [];
  page.on('request', req => { if (/808[4567]|\/mcp/.test(req.url())) forbidden.push(req.url()); });
  await login(page);
  const before = await request.get('http://127.0.0.1:8088/effects', { headers: { 'x-test-key': KEY } });
  const effectCount = (await before.json()).effects;
  const { runId } = await incidentAndRun(page);
  await expect(page.getByText('Deterministic fixture run.', { exact: true })).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`/api/ops/runs/${runId}`)).json()).status, { timeout: 60000 }).toBe('awaiting_approval');
  await expect(page.getByRole('cell', { name: 'get_service_metrics', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'get_dependency_status', exact: true })).toBeVisible();
  const run = await (await page.request.get(`/api/ops/runs/${runId}`)).json();
  expect(run.snapshot.tool_call_history).toHaveLength(5);
  expect(run.snapshot.candidate_root_cause).toBeTruthy();
  expect(run.snapshot.observations.every((o: object) => !/scenario_id|fault_id|worker-saturation/.test(JSON.stringify(o)))).toBeTruthy();
  await page.screenshot({ path: `${OUTPUT}/stage6-workspace.png`, fullPage: true });
  await page.getByRole('button', { name: 'Review action', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Exact approved arguments' })).toBeVisible();
  await page.screenshot({ path: `${OUTPUT}/approval.png`, fullPage: true });
  const approval = run.durable.approval;
  // A changed fingerprint is rejected by the real authorization API, even for this human.
  const modified = await page.request.post(`/api/ops/approvals/${approval.id}/decision`, {
    headers: { origin: ORIGIN }, data: { decision: 'approve', fingerprint: '0'.repeat(64) },
  });
  expect(modified.status()).toBe(409);
  await page.getByRole('button', { name: 'Approve action', exact: true }).click();
  await page.getByRole('dialog').getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Confirm approval', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Execute approved action', exact: true })).toBeVisible();
  const replay = await page.request.post(`/api/ops/approvals/${approval.id}/decision`, {
    headers: { origin: ORIGIN }, data: { decision: 'approve', fingerprint: approval.fingerprint },
  });
  expect(replay.status()).toBe(409);
  await page.getByRole('button', { name: 'Execute approved action', exact: true }).click();
  // Concurrent delivery must reuse the durable action, never apply another effect.
  await page.request.post(`/api/ops/runs/${runId}/resume`, { headers: { origin: ORIGIN }, data: {} });
  await expect.poll(async () => (await (await page.request.get(`/api/ops/runs/${runId}`)).json()).status, { timeout: 60000 }).toBe('verified');
  await page.goto(`/workspace/${runId}`);
  await expect(page.getByRole('heading', { name: 'Post-action verification' })).toBeVisible();
  await expect(page.getByText('human approved', { exact: true })).toBeVisible();
  const final = await (await page.request.get(`/api/ops/runs/${runId}`)).json();
  expect(final.durable.verification.outcome).toBe('verified');
  expect(final.durable.approval.approved_by).toBe('synthetic-browser-human');
  const after = await request.get('http://127.0.0.1:8088/effects', { headers: { 'x-test-key': KEY } });
  expect((await after.json()).effects).toBe(effectCount + 1);
  expect(forbidden).toEqual([]);
  expect(errors).toEqual([]);
  await info.attach('actual-run', { body: JSON.stringify(final, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: `${OUTPUT}/stage6-verified.png`, fullPage: true });
});

test('real browser: rejected approval never authorizes execution', async ({ page, request }) => {
  await login(page);
  const before = await (await request.get('http://127.0.0.1:8088/effects', { headers: { 'x-test-key': KEY } })).json();
  const { runId } = await incidentAndRun(page);
  await expect.poll(async () => (await (await page.request.get(`/api/ops/runs/${runId}`)).json()).status, { timeout: 60000 }).toBe('awaiting_approval');
  await page.getByRole('button', { name: 'Review action', exact: true }).click();
  await page.getByRole('button', { name: 'Reject action', exact: true }).click();
  await page.getByRole('dialog').getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Confirm rejection', exact: true }).click();
  await expect(page.getByText('human revoked', { exact: true })).toBeVisible();
  expect((await (await page.request.get(`/api/ops/runs/${runId}`)).json()).status).toBe('rejected');
  await expect(page.getByRole('button', { name: 'Execute approved action' })).toHaveCount(0);
  const resume = await page.request.post(`/api/ops/runs/${runId}/resume`, { headers: { origin: ORIGIN }, data: {} });
  expect(resume.status()).toBe(409);
  const after = await (await request.get('http://127.0.0.1:8088/effects', { headers: { 'x-test-key': KEY } })).json();
  expect(after.effects).toBe(before.effects);
});

test('real browser: investigation timeout is visible and carries no approval', async ({ page }) => {
  await login(page);
  const { runId } = await incidentAndRun(page, '0.1');
  await expect.poll(async () => (await (await page.request.get(`/api/ops/runs/${runId}`)).json()).status, { timeout: 30000 }).toBe('timed_out');
  await expect(page.getByText('Investigation time budget exhausted.', { exact: false })).toBeVisible();
  expect((await (await page.request.get(`/api/ops/runs/${runId}`)).json()).durable).toBeNull();
});

test('real browser: all read views render, mobile navigation and historical gates', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible();
  await expect(page.getByText('checkout-service', { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: `${OUTPUT}/stage6-overview-desktop.png`, fullPage: true });
  await page.goto('/evaluations');
  await expect(page.getByText('Recorded Stage 5 benchmark', { exact: false })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'B · LLM + tools' })).toBeVisible();
  await expect(page.locator('.gate').filter({ hasText: /unsupported/i }).getByText(/^fail$/i)).toBeVisible();
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible();
  await page.screenshot({ path: `${OUTPUT}/evaluations.png`, fullPage: true });
  await page.goto('/architecture');
  await expect(page.getByText('restart_simulated_worker', { exact: true })).toBeVisible();
  await page.getByText('06 · Human approval', { exact: true }).first().click();
  await page.screenshot({ path: `${OUTPUT}/architecture.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await page.getByRole('link', { name: 'Incidents', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Incidents', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'checkout-service', exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: `${OUTPUT}/stage6-mobile.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test('real browser: stopped backend is reported as unavailable, then recovers', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible();
  try {
    expect((await request.post('http://127.0.0.1:8088/outage', { headers: { 'x-test-key': KEY } })).ok()).toBeTruthy();
    await expect(page.getByText('Backend disconnected', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert').first()).toBeVisible();
    const response = await page.request.get('/api/ops/health/ready');
    expect(response.status()).toBe(503);
    expect((await response.json()).detail).toBe('BACKEND_UNAVAILABLE');
    await page.screenshot({ path: `${OUTPUT}/stage6-outage.png`, fullPage: true });
  } finally {
    expect((await request.post('http://127.0.0.1:8088/recover', { headers: { 'x-test-key': KEY } })).ok()).toBeTruthy();
  }
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible();
});
