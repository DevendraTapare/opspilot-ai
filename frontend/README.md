# OpsPilot operations dashboard

Local Next.js dashboard for actual incident evidence, LangGraph investigations,
human authorization and durable sandbox actions. Fixture runs are explicitly
labeled and perform **no LLM inference**. JavaScript dependencies are exact in
package.json/package-lock.json; Python dependencies remain in uv.lock.

## Windows startup and shutdown

Requires Node 24 LTS (tested 24.14.1), Python 3.12, uv and Docker Desktop with Linux containers.

```powershell
Set-Location D:\Projects\OpsPilot-AI
# Fresh setup only; preserves an existing .env:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-Local.ps1
uv sync --locked
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Dashboard.ps1
Invoke-RestMethod http://127.0.0.1:3000/api/ops/health/ready
Start-Process http://127.0.0.1:3000

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Stop-Dashboard.ps1
# Optionally stop only this project's backend services, retaining volumes:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Stop-Dashboard.ps1 -StopBackend
```

Startup applies migration 0004, provisions narrow database permissions, writes
ignored `.dashboard.env` and `frontend/.env.local`, and starts two tracked hidden
host processes. `-SkipBuild` reuses installed/built dependencies. Logs and the PID
manifest are under `artifacts/`. Stop verifies executable, start time and command
identity; it never terminates all Node/Python processes or deletes volumes.

Use **http://127.0.0.1:3000**, matching the configured origin. Sign in using the
human operator token privately retrieved from `.operator.env`; never paste it
into chat/docs/command arguments. The UI does not retrieve it automatically. The
random HttpOnly session lasts 30 minutes; sign-out revokes its digest in PostgreSQL.

## Demonstration journey

1. Sign in. Select **Simulate incident**, choose a service/scenario and explicitly
   confirm reset of only that fixture. Checkout worker saturation is suitable for
   the current deterministic fixture investigator.
2. Inspect incident metrics/logs. Launch a real-model investigation if configured,
   or explicitly select fixture mode. Inspect actual MCP calls, citations,
   hypotheses and the proposed remediation.
3. Open Approval center. Review the exact tool, target, arguments, evidence, risk,
   expiry and full action fingerprint. Approve/reject calls the real backend policy.
4. After approval, **Execute approved action** resumes the durable backend. Review
   measured verification and the persisted audit timeline in the workspace.

Actions are disabled by default. For deliberate local sandbox use an operator may
set `OPSPILOT_GATEWAY_ACTIONS_ENABLED=true` in private `.env`, rerun
`python -m scripts.initialize_dashboard`, recreate Compose `authorizer` and restart
the dashboard API. Both server-side flags must permit execution. Restore false
afterward. No irreversible or production action is supported.

Real mode inherits explicitly exported `OPSPILOT_AGENT_PROVIDER`, `_MODEL`,
`_BASE_URL` and optional `_API_KEY` from its launcher. Existing provider validation
applies; no automatic model choice or fallback occurs. No real model was configured
for Stage 6 verification. Do not describe fixture behavior as model reasoning.

For development, run `python -m opspilot.dashboard.server` from the project root
and `npm.cmd run dev -- --port 3000` from frontend in another terminal.

## Checks and isolated real-browser tests

```powershell
Set-Location D:\Projects\OpsPilot-AI\frontend
$env:npm_config_cache = Join-Path (Get-Location) '.cache\npm'
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.cache\ms-playwright'
npx.cmd playwright install chromium
```

Test backend terminal (only the dedicated test database; no main fixture resets):

The automated alternative, after `npm.cmd run build` and test DB startup, is
`.\.venv\Scripts\python.exe -m scripts.verify_dashboard` from the project root. It starts the isolated
stack and production Next build, runs Chromium, then stops only its own processes.
The harness reads `OPSPILOT_TEST_DB_PORT` from the private root configuration.

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --profile test up -d --wait test-db
Remove-Item -LiteralPath .\artifacts\stage6-browser-stack.stop -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m scripts.serve_dashboard_test
```

Test frontend terminal; these are **synthetic test-only** credentials:

```powershell
Set-Location D:\Projects\OpsPilot-AI\frontend
$env:OPSPILOT_DASHBOARD_BACKEND_URL = 'http://127.0.0.1:8087/'
$env:OPSPILOT_DASHBOARD_SERVICE_KEY = 'stage6-bff-test-key-' + ('k' * 40)
$env:NEXT_TELEMETRY_DISABLED = '1'
npm.cmd run dev -- --port 3001
```

Test runner terminal:

```powershell
Set-Location D:\Projects\OpsPilot-AI\frontend
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.cache\ms-playwright'
npm.cmd run test:e2e
Set-Content -LiteralPath ..\artifacts\stage6-browser-stack.stop 'stop'
# Stop the test Next.js terminal with Ctrl+C.
```

The harness uses an isolated UUID schema, actual simulator HTTP APIs, real TCP MCP
discovery/calls and PostgreSQL checkpoints. Port 8088 is a **test-only** controller
that stops/restarts the actual test API and counts committed effects. A deliberately
delayed fixture tests timeout handling. Neither mechanism exists in the runtime
dashboard. Playwright writes JSON and screenshots to frontend/test-results; traces
are disabled to avoid recording login input. Tests use synthetic humans, not a
claim that a person attended the automated approval.

Stage 7 adds an absolute five-second JSON body deadline to the proxy. Rotating a
human registry credential invalidates old sessions; legacy cookies also require
login again after upgrading. Sessions remain server-side and opaque to JavaScript.
See [Stage 7 review](../docs/STAGE_7_REPORT.md) for actual security test scope.

See [architecture](../docs/FRONTEND_ARCHITECTURE.md) and
[actual Stage 6 results](../docs/STAGE_6_REPORT.md).

## Release verification

Stage 8 uses `python -m scripts.verify_release_browser` from the root after building
Next and starting the isolated review database. It generates new runtime test
credentials and unique `artifacts/stage8/` evidence paths, preserving Stage 6 files.
Optional `--grep` isolates a test title for a separately labeled recheck. Failures
propagate; no automatic retry makes a failing combined run appear green.
Biome runs four explicit safety rules; strict TypeScript checks remain separate.
The evaluation view reads baseline gates from the selected historical split, not
the real-model-only release assessment. [Stage 8 results](../docs/STAGE_8_REPORT.md).
