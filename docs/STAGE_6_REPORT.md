# Stage 6 — Operations dashboard verification

Verification date: **2026-11-03**, Windows, Asia/Calcutta.

**Status: CONDITIONAL.** The dashboard and real-browser lifecycle work. No real
model is configured, and the full regression had timeout failures that passed in
isolation; it is not represented as a clean all-pass run.

## Implemented scope

Six responsive light-theme dashboard views: overview, incident detail/list,
agent workspace, approval center, evaluations and system architecture. They use
actual backend records, real MCP tool history and persisted approval/action states.
Architecture diagrams are implementation maps; Stage 5 evaluation aggregates are
explicitly historical. There is no static live incident dataset or fake success.

The local Next.js BFF protects server credentials. The dashboard API authenticates
human operators, persists/revokes sessions, enforces origin/body/rate/scope limits,
and reuses the existing exact-fingerprint approval transaction. Approving and
executing are separate operations. Durable action delivery, reconciliation and
post-action measurement remain the Stage 4 implementation. Investigations persist
progress and become interrupted on restart rather than silently repeating inference.

## Actual files

New frontend source/configuration: `frontend/package.json`, `package-lock.json`,
`tsconfig.json`, `next.config.ts`, `postcss.config.mjs`, `.npmrc`,
`src/app/layout.tsx`, `src/app/[[...view]]/page.tsx`, `src/app/globals.css`,
`src/app/api/ops/[...path]/route.ts`, `src/components/dashboard.tsx`, `src/lib/api.ts`,
`playwright.config.ts`, `tests/lifecycle.spec.ts`, `README.md`.
Next generated `frontend/next-env.d.ts` and its version-specific `AGENTS.md`.

New backend: `opspilot/dashboard/{__init__,api,config,jobs,readmodels,security,server}.py`,
`migrations/versions/0004_dashboard.py`, `tests/test_dashboard.py`.

New scripts: `scripts/initialize_dashboard.py`, `serve_dashboard_test.py`,
`verify_dashboard.py`, `Start-Dashboard.ps1`, `Stop-Dashboard.ps1`.
New docs: this report and `docs/FRONTEND_ARCHITECTURE.md`.

Updated existing investigation optional progress/run-ID support, shared human
approval transaction, bounded audit reports, models, migration readiness,
provisioning revision support, test-report connection-string redaction, ignores and current README/architecture/security/
roadmap/manifest documents. Historical Stage 1–5 reports are preserved. Private
`.dashboard.env` and `frontend/.env.local` are generated and ignored.

## Versions

| Component | Tested version |
|---|---|
| Node / npm | 24.14.1 / 11.11.0 |
| Next.js | 16.4.4 |
| React / React DOM | 19.3.1 |
| TypeScript | 7.0.2 |
| Tailwind / PostCSS plugin | 4.3.4 |
| React Flow | @xyflow/react 12.12.1 |
| Lucide | lucide-react 1.67.0 |
| Inter local font | @fontsource-variable/inter 5.3.0 |
| Playwright | 1.64.1 |
| Actual browser | Chromium 156.0.8078.4, Playwright build 1248 |
| Python | Host 3.12.3; existing Docker 3.12.14 |
| PostgreSQL | Existing pinned 18.6 image |

Frontend dependencies are exact and locked. Existing Python uv.lock is preserved.
No LLM package, paid API, deployment or uncontrolled agent was added.

## Actual browser evidence

The production Next build was exercised by real Chromium against a generated schema
in the dedicated local PostgreSQL test database. The harness used actual simulator
HTTP APIs, real TCP MCP discovery/tool calls, persistent PostgreSQL checkpoints
and **synthetic authenticated test humans**. Main database actions stayed disabled.

Final complete run: **5 passed, 0 failed/skipped/flaky**, 169.975s against the
production build. An earlier complete run also passed all five in 126.797s. Coverage:

1. Sign in, start checkout incident, launch a fixture investigation, inspect five
   actual MCP calls/evidence, reject a modified fingerprint, approve the exact
   action, reject approval replay, issue duplicate resume requests, observe one
   action effect, verify recovery and inspect the persisted final timeline.
2. Reject an approval, reject subsequent resume, and verify zero additional effects.
3. Exhaust the real investigation deadline with a deliberately delayed fixture;
   show timeout and no durable approval request.
4. Render historical evaluation/architecture views and navigate at 390px mobile width.
5. Actually stop the dashboard test API, observe BFF 503/disconnected state, restart
   the API and observe restored connection. This was not a mocked fetch success.

The test-only lifecycle controller is outside the runtime API. Browser page errors
and direct browser connections to privileged backend/MCP ports were checked.
Screenshots were captured and visually inspected. Final mobile screenshot waits
for actual table rows before capture rather than treating loading as a data view.

Actual final successful investigation:

- Mode/model: `fixture` / `worker-observation-fixture-v1`; **no real model used**.
- Tool calls: `get_incident`, `get_service_metrics`, `search_service_logs`,
  `get_dependency_status`, `list_recent_deployments`.
- Evidence: checkout 30 requests, 27 errors (90%), worker utilization 100%; sampled
  dependencies healthy. Fixture metadata/cause identifiers absent from observations.
- Diagnosis: local worker capacity exhausted; alternative dependency failure
  compared. Confidence 0.8 with explicit single-window uncertainty.
- Proposed/executed sandbox action: `restart_simulated_worker` on checkout-service,
  signed by the independently authenticated synthetic human.
- Investigation latency: 3,328ms; whole browser journey: 38,568ms.
- Inference tokens: none. Eleven fixture decision calls are not eleven LLM calls;
  estimated model cost is unavailable/not applicable, not a paid-model benchmark.
- Verification: 12 checkout requests, zero errors, p95 53ms, worker utilization
  19.9132%; dependency verification windows also had zero errors.
- Audit includes `human_approved`, action preparation, actual MCP execution,
  `action_committed`, verification tool call, `verification_verified`, result
  persistence and `workflow_finished`. Duplicate resume caused exactly one ledger effect.

Evidence: `frontend/test-results/stage6-results.json`, screenshots under that
directory, `artifacts/stage6-browser-actual-run-final.json` and ignored local run logs.

## Other checks

- TypeScript and optimized Next production build: passed.
- Final Ruff lint/format: passed.
- Corrected portable dashboard API suite: 9 passed, 9 PostgreSQL variants skipped
  before Docker was available (`artifacts/stage6-dashboard-portable.xml`).
- Full PostgreSQL-backed regression before the final deadline regression addition:
  **262 passed, 40 skipped, 1 failed, 2 setup
  errors**, 783.08s, 305 collected cases (`artifacts/stage6-regression.xml`). The
  errors were existing 3s PostgreSQL connection timeouts in
  `test_bad_config_deployment_and_rollback[postgres]` and
  `test_measured_security[postgres-stale]`. The failure was an HTTP read timeout in
  `test_approved_actions_and_duplicate_requests[postgres-reset_simulated_dependency-payment-service-payment-unavailable]`.
- Focused rerun with no concurrent build/startup load: **21 passed, 0 failed/skipped**,
  34.07s (`artifacts/stage6-focused.xml`), including all 18 dashboard API variants
  (SQLite and PostgreSQL) and all three above cases. Existing action/test deadlines
  were not increased to make these tests pass. The full run remains recorded as
  non-clean. Skips include SQLite-only exclusions for PostgreSQL guarantees,
  unconfigured real-model smoke and live-API tests without opt-in credentials.
  An earlier interrupted regression has no final result and is not counted.
- After the deadline fix, agent suite: **32 passed, 3 skipped**, 10.01s
  (`artifacts/stage6-agent-deadlines.xml`). Both model and tool total-budget expiry,
  per-call failures, cancellation and no fallback are checked. The new test covers
  a total tool deadline distinct from a per-call timeout. This scoped rerun and
  the final real-MCP browser suite validate the fix; no second full-suite pass is claimed.
- Frontend source/browser-asset credential scan: 13 private values checked across
  24 files, zero matches (`artifacts/stage6-credential-audit.json`). Server bundles
  are intentionally outside the browser scan; they remain private server code.
- Actual startup reached ready, reported real-model unavailable/actions disabled,
  and actual shutdown stopped only the two tracked hosts; listeners 3000/8086 closed.
  A repeat under regression load hit a local DB connection timeout during
  provisioning. Stage 6 provisioning now has a bounded 10s connection allowance;
  the final startup completed and again reached ready with actions disabled.

Early browser failures found a normalized loopback-origin mismatch and an overly
short timeout for four-step simulator setup. Both were fixed before the passing
complete run. A test-client DELETE compatibility error was also corrected.

A later repeat had **3 browser checks pass / 2 fail** before the final correction:
login returned a real database-unavailable error, and a timer-rounding race classified
a total investigation deadline as generic failure. The investigator now uses the
timer's expiry state and selected deadline, preserving distinct per-call failures
and existing timeout codes. The browser harness warms four bounded database-pool
connections before Chromium startup; action/tool budgets are unchanged. The final
five-check run above passed after these changes. The pre-fix repeat report is
retained as `artifacts/stage6-browser-repeat-before-deadline-fix.json`.

## Environment and limitations

The interruption stopped Docker/host processes. After Docker restart Windows had
reserved ports 55409–55508, including the old database bindings. Only this project's
private connection files and Compose bindings moved to **56432 main / 56433 test**;
the existing main volume was retained. Windows port reservations were not changed.

Final local services: frontend `127.0.0.1:3000`, dashboard API `127.0.0.1:8086`,
existing simulator API `127.0.0.1:8084`, MCP `127.0.0.1:8085`; the four main Compose
services are healthy. Test HTTP hosts 3001/8087/8088 were stopped by their owner.
The main database still had three services, nineteen historical incidents, one
historical durable run and **zero signed grants/action executions** at the final
read check. No Stage 6 main-database investigation or human session was created.
The temporary test database container is stopped; no volume was removed. A
machine-readable result is in `artifacts/stage6-verification-summary.json`.

No real provider is configured. This stage demonstrates actual orchestration,
protocol use, approval authorization, transactional sandbox effects and measured
verification with a deterministic investigator; it does not validate LLM reasoning
quality. Stage 5's existing blocked evaluation gate remains visible.

This is a loopback local application with one dashboard job-manager process,
30-minute high-entropy-token human sessions and trusted local OS/admin access.
It is not a remote multi-user identity deployment. Investigation snapshots persist
after nodes but do not make Stage 3 inference restartable; interrupted inference
requires an explicit new run. Stage 4 durable action guarantees remain independent.
Simulator setup spans transactions and can partially complete on timeout. Full audit
exports remain available through the CLI if bounded dashboard views are truncated.

## Startup and stopping

```powershell
Set-Location D:\Projects\OpsPilot-AI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Dashboard.ps1
Invoke-RestMethod http://127.0.0.1:3000/api/ops/health/ready
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Stop-Dashboard.ps1
```

See frontend/README.md for prerequisites, isolated browser reruns and optional
project-backend shutdown. No commit, push, cloud deployment, unrelated project
change or Stage 7 work was performed.
