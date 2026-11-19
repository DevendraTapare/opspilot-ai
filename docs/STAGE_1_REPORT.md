# Stage 1 verification report

Date: **2026-11-02**, Asia/Calcutta. Project: `D:\Projects\OpsPilot-AI`.

## Verdict: PASS

Stage 1 is implemented and verified with real PostgreSQL, Docker containers, and
HTTP requests. No other project was edited. No commit, push, deployment, paid API,
frontend, LangGraph, or Stage 2 implementation was performed.

## Files created

The exact authored-file inventory is [FILE_MANIFEST.md](FILE_MANIFEST.md). It includes
the backend package, isolated service models, migrations, five test modules,
PowerShell initialization and verification scripts, Dockerfile, Compose stack,
Pydantic API contracts, dependency lock, configuration example, and documentation.
Generated `.env` contains local secrets and is excluded from Git and image builds.
Local virtual environments, caches, and verification artifacts are also ignored.

## Actual technology versions

| Technology | Version |
|---|---|
| Python in Docker | 3.12.14 |
| Python used for host tests | 3.12.3 |
| FastAPI | 0.162.0 |
| Pydantic | 2.14.2 |
| Pydantic Settings | 2.16.2 |
| PostgreSQL server | 18.6, Debian package 18.6-1.pgdg12+2 |
| SQLAlchemy | 2.0.55 |
| Alembic | 1.20.1 |
| Psycopg / binary driver | 3.3.6 |
| Uvicorn | 0.54.0 |
| Starlette | 1.10.0 |
| Pytest | 9.2.0 |
| Ruff | 0.17.3 |
| HTTPX2 test client | 2.16.0 |
| uv | 0.11.23 |
| Docker Engine | 29.9.2 |
| Docker Desktop | 4.97.0 |
| Docker Compose | 5.6.1 |

`uv.lock` locks direct/transitive dependencies and artifact hashes, including
Windows/Linux selections. `uv lock --check --offline` passed. Docker base images
are pinned by immutable digest in the Dockerfile and Compose file. HTTPX2 follows
the current [Starlette test-client interface](https://starlette.dev/testclient/).

## Working APIs and behavior

The running API is at `http://127.0.0.1:8084`, with `/docs` and `/openapi.json`.
All 17 application operations and their concrete schema names are listed in
[API.md](API.md). They cover health/readiness, services, scenario catalog, fault
history/activation/deactivation, explicit fixture resets, single requests and
workloads, incidents/events, metric summaries, request logs, and deployment events.

All mutation endpoints require a bearer token. Missing/incorrect tokens return
401. Invalid requests return 422; duplicate active faults return 409; unknown
incident/fault UUIDs return 404. Readiness checks the live database, migration
revision, and service fixtures. Alembic reports `0001_stage1 (head)`.

## Fault scenarios: actual HTTP evidence

These values came from `python -m scripts.verify_stack` against the running API.
All fixtures were explicitly selected and reset to seed 42 before each case.
Each case used one request except saturation, which used 30 simultaneous requests.
Wall duration includes persistence and transport overhead; summary p95 is modeled
execution time. The workload envelope uses HTTP 200 and carries per-request statuses.

| Scenario | HTTP status | Requests / errors | p95 latency | Measured wall duration |
|---|---:|---:|---:|---:|
| Healthy baseline, checkout | 200 | 1 / 0 | 43ms | 225.819ms |
| Slow checkout | 200 | 1 / 0 | 593ms | 793.973ms |
| Payment unavailable | 503 | 1 / 1 | 53ms | 74.581ms |
| Inventory DB exhaustion | 503 | 1 / 1 | 92ms | 112.688ms |
| Worker saturation, payment burst | 200 envelope | 30 / 20 | 100ms | 164.202ms |
| Bad simulated configuration | 500 | 1 / 1 | 17ms | 45.532ms |

Inventory exhaustion reached 100% modeled connection-pool utilization; saturation
reached 100% modeled worker utilization. Payment failure propagated to checkout as
HTTP 502 in both API and live integration tests. Unrelated inventory fixtures and
observations remained unchanged in the selected-isolation tests.

## Executed verification

| Check | Actual result |
|---|---|
| Host Pytest suite | **52 passed, 51 skipped, 0 failed**, 39.44s |
| Docker suite, SQLite + PostgreSQL + live HTTP | **101 passed, 2 skipped, 0 failed**, 81.34s |
| Ruff lint | Passed |
| Ruff format check | Passed |
| Dependency lock consistency | Passed |
| Compose configuration and final readiness | Passed |
| All six real HTTP scenarios | Passed |
| PostgreSQL/API restart persistence | Passed |
| Optional traffic generation | Actual authenticated batches completed |
| Optional traffic shutdown | Signal handling verified; exit code **0** |
| Structured application-log audit | Initial 307 and final 101 records checked; all JSON, no token/password leakage |

The Docker run executed the same API tests on PostgreSQL and SQLite. Its two
skips were SQLite variants of PostgreSQL-only row-lock and migration-round-trip
tests; both PostgreSQL variants passed. No PostgreSQL or live HTTP tests were
skipped in that run. Host skips represent the intentionally absent host test-DB
and live-API environment settings, plus those two SQLite-only exclusions.

Tests cover healthy baseline, every fault's execution effect, exact counts/error
rates/percentiles/status distributions, incidents, deduplication, events and logs,
recovery, deployment rollback, strict validation, authentication, conflict handling,
pagination, cross-service isolation, selected/repeated resets, deterministic replay
of every scenario, schema/model agreement, rollback, engine reconnection, and
concurrent fault activation.

After HTTP scenario generation, both the application PostgreSQL container and API
were restarted while retaining the project's volume. Every saved incident ID,
event list, metric summary, and request-log collection remained available. Reset
state also persisted. The optional worker was subsequently exercised separately.
An initial forced worker stop was corrected with explicit signal handling and a
20-second grace period; the updated container exited cleanly with code 0.

Evidence retained under `artifacts/`:

- `local-tests.xml`: host suite's real JUnit results.
- `docker-tests.log`: full Docker build and successful integration-test output.
- `http-verification.json`: six HTTP observations and successful restart check.
- `versions.json`: observed host dependency versions.
- `log-verification.json`: most recent JSON/secret-leak audit.
- `final-state.json`: final readiness, service fixture state, active faults, incidents.
- `compose-start.log`, `docker-status.json`: final startup/status evidence.
- `worker-verification.log`: updated traffic-worker build/start evidence.

The executed full Docker invocation wrote JUnit inside its disposable container;
its persistent evidence is `docker-tests.log`. The documented default test command
now mounts `artifacts/` and writes `docker-tests.xml` there on subsequent runs.

## Docker and final fixture state

Only the `opspilot-stage1` Compose project was operated on. The API and application
PostgreSQL are healthy and left running. The migration container exited with code
0. The optional traffic worker and disposable test database are stopped; the worker
was verified to exit with code 0. No unrelated containers or volumes were removed.

The application data volume is `opspilot-stage1_opspilot-data`. API and database
host ports bind only to `127.0.0.1:8084` and `127.0.0.1:55432`. All three explicitly
selected fictional fixtures were restored to seed 42 and cursor 0. No active
faults or open incidents remain; resolved histories are retained.

## Startup, checks, and shutdown

```powershell
Set-Location D:\Projects\OpsPilot-AI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-Local.ps1
docker compose up -d --build --wait
Invoke-RestMethod http://127.0.0.1:8084/health/ready
docker compose ps -a
docker compose --profile test run --build --rm tests
docker compose --profile traffic --profile test down
```

The final command preserves the application's database volume. Full scenario and
development commands are in [README.md](../README.md).

## Known limitations

- Services are logical models inside one simulator backend, not three independent
  production service processes. Worker and database exhaustion affect bounded
  modeled resources; actual host workers and PostgreSQL capacity are protected.
- Queues/resource occupancy restart for each workload. Active faults, seeds,
  cursors, fixture generations, and observations persist across workloads.
- Metrics use virtual execution time; real elapsed HTTP duration adds persistence
  and scheduling overhead. Observation transactions commit before wall-time replay.
- Traffic is on demand unless the optional profile is enabled. Disable that worker
  before deterministic resets/replay. High-load healthy fixtures may still degrade.
- One active fault is supported per service. Workloads are bounded to 50 requests
  with a 0–100ms arrival interval. Histories page at a maximum of 500 rows per call.
- Incidents use fixed 20% error-rate / 300ms p95 thresholds and one healthy-window
  recovery. There is no advanced causal diagnosis or autonomous remediation.
- Read APIs are unauthenticated local observations. There are no users, TLS,
  distributed rate limits, or Internet-hosting controls. The database role is for
  this disposable local simulator, not a production authorization design.
- Retention/downsampling and durable queues spanning bursts are future work.
  PostgreSQL is the application backend; SQLite exists only for portable tests.

Stage 1 verification is complete. Stop here; Stage 2 is documented only as future scope.
