# Created file inventory

Authored source, configuration, test, and documentation inventory through Stage 6.

## Stage 6 additions

- `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`
- `frontend/next.config.ts`, `frontend/postcss.config.mjs`, `frontend/next-env.d.ts`
- `frontend/src/app/layout.tsx`, `frontend/src/app/[[...view]]/page.tsx`
- `frontend/src/app/globals.css`, `frontend/src/app/api/ops/[...path]/route.ts`
- `frontend/src/components/dashboard.tsx`, `frontend/src/lib/api.ts`
- `frontend/playwright.config.ts`, `frontend/tests/lifecycle.spec.ts`, `frontend/README.md`
- `opspilot/dashboard/{__init__,api,config,jobs,readmodels,security,server}.py`
- `migrations/versions/0004_dashboard.py`, `tests/test_dashboard.py`
- `scripts/initialize_dashboard.py`, `scripts/serve_dashboard_test.py`, `scripts/verify_dashboard.py`
- `scripts/Start-Dashboard.ps1`, `scripts/Stop-Dashboard.ps1`
- `docs/FRONTEND_ARCHITECTURE.md`, `docs/STAGE_6_REPORT.md`

Existing model, investigation callback, shared human policy, bounded report,
readiness, provisioning and current architecture/security documentation are updated.
Historical Stage 1–5 reports remain unchanged. Node/Python/browser caches,
private environment files, build output and test artifacts are generated/ignored.
Stage 1 introduced 42 files; Stage 2 added 20; Stage 3 adds the 12 files below.

## Stage 5 additions

- opspilot/observability.py
- evaluations/__init__.py
- evaluations/runners/__init__.py
- evaluations/runners/contracts.py
- evaluations/runners/dataset.py
- evaluations/runners/environment.py
- evaluations/runners/subjects.py
- evaluations/runners/metrics.py
- evaluations/runners/benchmark.py
- evaluations/runners/operations.py
- evaluations/runners/release.py
- evaluations/datasets/README.md
- evaluations/datasets/v1/manifest.json
- evaluations/datasets/v1/calibration.jsonl
- evaluations/datasets/v1/development.jsonl
- evaluations/datasets/v1/held_out.jsonl
- evaluations/reports/README.md
- tests/test_evaluations.py
- tests/test_eval_protocol.py
- tests/test_eval_operations.py
- docs/EVALUATION_METHODOLOGY.md
- docs/STAGE_5_REPORT.md

Generated benchmark plans/results, operational trials/JUnit and PID-suffixed traces
are listed in STAGE_5_REPORT.md. Stage 5 updates existing workflow/provider/MCP,
incident, approval/action/verification and logging modules for manual telemetry;
README/current architecture/roadmap, image/report exclusions and dependency lock
are updated. Historical Stage 1–4 reports remain historical records.

## Stage 4 additions

- docs/DURABLE_EXECUTION.md
- docs/APPROVAL_SECURITY.md
- docs/STAGE_4_REPORT.md
- migrations/versions/0003_durable.py
- opspilot/durable/__init__.py
- opspilot/durable/cli.py
- opspilot/durable/client.py
- opspilot/durable/contracts.py
- opspilot/durable/gateway.py
- opspilot/durable/operator.py
- opspilot/durable/persistence.py
- opspilot/durable/policy.py
- opspilot/durable/repository.py
- opspilot/durable/workflow.py
- scripts/initialize_durable.py
- scripts/verify_durable_boundaries.py
- tests/durable_crash_worker.py
- tests/test_durable.py

Stage 4 updates models, readiness, typed MCP contracts/client/dispatch, gateway
grant validation, dependency lock, private-file exclusions, optional test DB
loopback port, test-report secret redaction, setup verification and documentation.
Generated `.runner.env` and `.operator.env` are ignored and excluded from images.
Stage 4 artifacts include crash/recovery test results, scoped privilege checks,
separately approved recovery examples and retained audit timelines.

## Stage 3 additions

- docs/AGENT_ARCHITECTURE.md
- docs/STAGE_3_REPORT.md
- opspilot/agent/__init__.py
- opspilot/agent/cli.py
- opspilot/agent/evidence.py
- opspilot/agent/fixtures.py
- opspilot/agent/mcp.py
- opspilot/agent/providers.py
- opspilot/agent/schemas.py
- opspilot/agent/workflow.py
- scripts/verify_agent.py
- tests/test_agent.py

Stage 3 also updates dependency declarations/lock, `.env.example`, README,
architecture, security boundaries, roadmap, and this inventory. It does not
change Stage 1/2 API, simulator, gateway, migration, or database contracts.

## Existing Stage 1/2 files

- .dockerignore
- .env.example
- .gitignore
- .python-version
- Dockerfile
- README.md
- alembic.ini
- artifacts/.gitkeep
- compose.yaml
- docs/API.md
- docs/ARCHITECTURE.md
- docs/DEVELOPMENT_ROADMAP.md
- docs/FILE_MANIFEST.md
- docs/MCP_TOOLS.md
- docs/SECURITY_BOUNDARIES.md
- docs/STAGE_1_REPORT.md
- docs/STAGE_2_REPORT.md
- migrations/env.py
- migrations/script.py.mako
- migrations/versions/0001_stage1.py
- migrations/versions/0002_gateway.py
- opspilot/__init__.py
- opspilot/api.py
- opspilot/config.py
- opspilot/db.py
- opspilot/faults.py
- opspilot/gateway/__init__.py
- opspilot/gateway/approvals.py
- opspilot/gateway/approve.py
- opspilot/gateway/authorizer.py
- opspilot/gateway/client.py
- opspilot/gateway/contracts.py
- opspilot/gateway/mcp_server.py
- opspilot/gateway/observations.py
- opspilot/gateway/security.py
- opspilot/gateway/stdio.py
- opspilot/incidents.py
- opspilot/logging.py
- opspilot/main.py
- opspilot/models.py
- opspilot/schemas.py
- opspilot/simulator/__init__.py
- opspilot/simulator/engine.py
- opspilot/telemetry.py
- opspilot/uvicorn-logging.json
- opspilot/worker.py
- pyproject.toml
- scripts/Initialize-Local.ps1
- scripts/audit_logs.py
- scripts/initialize_gateway.py
- scripts/mcp_client.py
- scripts/provision_gateway_db.py
- scripts/verify_gateway_boundaries.py
- scripts/verify_mcp.py
- scripts/verify_stack.py
- tests/conftest.py
- tests/test_api.py
- tests/test_live.py
- tests/test_mcp.py
- tests/test_postgres.py
- tests/test_safety.py
- uv.lock

## Generated local files

- .env: independent local secrets; ignored and excluded from images
- .venv/, .uv-cache/, .pytest_cache/, .ruff_cache/, Python bytecode caches
- artifacts/pytest-*/: owned temporary test fixtures
- Original Stage 1 evidence remains under artifacts/.
- Current Stage 2 evidence:
- artifacts/stage2-compose.log
- artifacts/stage2-docker-tests.log
- artifacts/stage2-docker-tests.xml
- artifacts/stage2-final-state.json
- artifacts/stage2-live-mcp.json
- artifacts/stage2-live-unavailable.json
- artifacts/stage2-local-tests.log
- artifacts/stage2-local-tests.xml
- artifacts/stage2-mcp-local.xml
- artifacts/stage2-protocol-final.log
- artifacts/stage2-protocol-final.xml
- artifacts/stage2-regression.xml
- artifacts/stage2-security-verification.json
- artifacts/stage2-stdio-client.log
- artifacts/stage2-test-summary.json

Stage 3 evidence is under `artifacts/stage3-*`: local and Docker JUnit/logs,
fixture investigation records, a separate operator trigger record, retained startup
and timeout attempts, and verification summaries. Exact results are in STAGE_3_REPORT.md.

Stage 4 evidence is under `artifacts/stage4-*`: separate full regression and
focused rerun reports, final PostgreSQL durability results, hard-process recovery,
restricted-role checks, fixture handoff/pending approval, independently approved
test recovery, final container state and bounded credential scans. Exact results
and guarantee boundaries are in STAGE_4_REPORT.md.

Stage 7 additions and changes:

- `compose.stage7.yaml`, private ignored `.stage7.env`, updated `.gitignore`/`.dockerignore`.
- `opspilot/topology.py`, `opspilot/durable/evidence.py`.
- Evidence binding in `agent/evidence.py`/`workflow.py`; durable submission attestation.
- Credential-bound session digests in `dashboard/security.py`; bounded dashboard and authorizer bodies.
- Absolute body deadline in `frontend/src/app/api/ops/[...path]/route.ts`.
- `tests/test_stage7_boundaries.py`, `test_stage7_integrations.py`, `test_stage7_frontend.py`;
  session-storage assertion update in `tests/test_dashboard.py`.
- `reviews/`: case catalog, pytest evidence plugin, report renderer and isolated simulator child.
- `scripts/initialize_stage7.py`, `scripts/review_stage7.py`.
- `docs/SECURITY_REVIEW.md`, `RELIABILITY_REPORT.md`, `STAGE_7_REPORT.md`;
  current architecture/security/roadmap/readme updates, historical Stage 1–6 reports preserved.
- `artifacts/stage7/`: unique per-run test ledgers, JUnit, logs and case matrices;
  earlier Stage 7 reproductions and fix regressions retained under `artifacts/stage7-*`.

Stage 8 release preparation:

- Rewritten `README.md`, new `CONTRIBUTING.md` and `SECURITY.md`.
- `docs/LANGGRAPH_STATE_MACHINE.md`, `THREAT_MODEL.md`, `DEPLOYMENT_ARCHITECTURE.md`,
  `DEMO_SCRIPT.md`, `RESUME_HIGHLIGHTS.md`, `RELEASE_CHECKLIST.md`, `STAGE_8_REPORT.md`.
- `docs/screenshots/`: seven actual Chromium PNGs, captions and provenance hashes.
- `docs/evidence/`: reviewed historical benchmark and current release aggregates/index.
- `.github/workflows/ci.yml`, `.github/dependabot.yml`; no remote execution or deployment.
- `scripts/release_hygiene.py`, `verify_release_browser.py`, `docker_release_smoke.py`,
  `export_release_evidence.py`; unique private verification paths.
- `compose.release-check.yaml`; isolated runtime startup and retained private volume.
- Updated Docker test target includes accumulated scripts/reviews/evaluation support;
  runtime image continues to exclude fixture datasets and operator scripts.
- Biome configuration/dependency/script; preserved Playwright output paths and fresh
  release test credentials; baseline gate rendering fix and browser assertion.
- `tests/test_release_hygiene.py`; runtime-generated canaries in three existing test
  modules; updated current architecture/roadmap/frontend guides and ignore policies.
- Historical Stage 1–7 reports and evaluation originals remain unchanged.

No other project was modified. No commit, push, deployment or unapproved main-data
remediation was performed. Stage 6 test actions use isolated schemas and synthetic humans.
