# Stage 2 verification report

Date: **2026-11-02**, Asia/Calcutta. Workspace: `D:\Projects\OpsPilot-AI`.

## Verdict: PASS for the requested local Stage 2 scope

A real MCP interface and a separate least-privilege authorization service are
implemented. Stage 1's simulator, admin APIs, fixtures, and durable history remain
functional. No LLM, autonomous agent, paid API, production credentials, deployment,
commit, push, or Stage 3 implementation was introduced.

## What was created and changed

- `opspilot/gateway/contracts.py`: strict input models, typed results, bounded
  errors, and the explicit seven-read/three-action registry.
- `mcp_server.py`, `stdio.py`, `client.py`: official SDK protocol server,
  authenticated Streamable HTTP, credential-scoped stdio, and explicit SDK clients.
- `authorizer.py`, `security.py`, `observations.py`: independent caller/service
  enforcement, signed service assertions, limits/deadlines, fixed observation
  queries, response validation, and persistent audits.
- `approvals.py`, `approve.py`: signed, scoped, expiring, single-use grants and
  a separate human operator CLI. There is no approval-issuance tool or HTTP API.
- `migrations/versions/0002_gateway.py`: three additional tables without removing
  or rewriting Stage 1 data. ORM models include approvals, executions, and audits.
- `tests/test_mcp.py`: actual TCP/HTTP and stdio protocol tests, positive scoped
  actions, negative cases, PostgreSQL concurrency, and restricted-role execution.
- `scripts/initialize_gateway.py`, `provision_gateway_db.py`, `mcp_client.py`,
  `verify_mcp.py`, `verify_gateway_boundaries.py`: local setup, independent secrets,
  limited DB-role provisioning, working clients, and retained live evidence.
- Compose adds optional `mcp` and `authorizer` services. MCP binds only to
  `127.0.0.1:8085`; the authorizer has no host port. `uv.lock`, `.env.example`,
  README, architecture, roadmap, and file inventory were updated.
- Required documentation: [MCP_TOOLS.md](MCP_TOOLS.md),
  [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md), and this report.

The exact current source inventory is [FILE_MANIFEST.md](FILE_MANIFEST.md).
Stage 1's verification report is retained as historical evidence.

## Versions and protocol compatibility

| Component | Observed/locked version |
|---|---|
| MCP Python SDK | **2.3.0** |
| MCP types | **2.3.0** |
| MCP protocol used on the wire | **2026-07-28** |
| MCP server application version | 0.2.0 |
| Python, Docker / host | 3.12.14 / 3.12.3 |
| FastAPI / Pydantic | 0.162.0 / 2.14.2 |
| PostgreSQL / SQLAlchemy | 18.6 / 2.0.55 |
| Alembic / Psycopg | 1.20.1 / 3.3.6 |
| HTTPX2 | 2.16.0 |
| Pytest / Ruff | 9.2.0 / 0.17.3 |

The current [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
and the [official SDK low-level server interface](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)
were checked. The implementation uses `mcp.server.Server`, not a custom imitation
of MCP. Real SDK clients exercise `server/discover`, `tools/list`, and `tools/call`
with the current protocol metadata and result format. Pydantic-generated JSON
schemas appear in discovery, and live results are checked against output schemas.
Unknown tools return a JSON-RPC `-32602` error with bounded `UNKNOWN_TOOL` data;
registered-tool failures return typed structured results with `isError=true`.

Both Streamable HTTP and stdio discovery/calls were exercised. The stdio example
runs both SDK peers inside the Linux container, avoiding Windows Docker-exec
pipes as the protocol transport. Its startup allowance is bounded to 30 seconds;
the backend's three-second tool deadline is unchanged. Earlier cold-start
timeouts were investigated, and the updated path was exercised successfully.

**HTTP authorization compatibility limit:** this local endpoint uses pre-provisioned
bearer credentials. It does not implement browser OAuth login, PKCE, authorization
server discovery, or the complete optional HTTP OAuth profile. Clients must supply
their configured local token. The stdio path uses launch-environment credentials.
This report claims verified current-protocol discovery/tool interoperability, not
formal conformance to every optional MCP feature or the OAuth profile. See the
[authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
and the explicit boundaries in SECURITY_BOUNDARIES.md.

## Tools and real effects

Read tools: `list_incidents`, `get_incident`, `get_service_health`,
`get_service_metrics`, `search_service_logs`, `list_recent_deployments`, and
`get_dependency_status`. Every read is constrained to a permitted service. Incident
events and history pages are bounded. Health includes its observation time and
can explicitly report unknown when measurements are absent or stale relative to
a fault. Log search is literal and parameterized.

Action tools: `restart_simulated_worker`, `rollback_simulated_configuration`, and
`reset_simulated_dependency`. The separate authorizer checks its disable flag,
caller permissions, service scope, approval signature, subject/action/service/fault
binding, expiry, consumption state, execution UUID, and current fault state. Only
the corresponding simulated fault can be deactivated. No host command runs, and
seeds/cursors/other fixtures are not reset. Configuration rollback is persisted.

Positive action tests used **synthetic signed grants in dedicated test schemas**,
with the backend action switch enabled only in those fixtures. Before each action,
Stage 1's workload API produced errors; after the real MCP action, the same workload
returned zero errors. Repeat execution IDs and reused grants were denied. The
running application stayed action-disabled and received no human approvals or
action executions. An actual human approval was not fabricated or automated.

## Executed tests and retained results

| Verification | Actual result |
|---|---|
| Full Docker regression: Stage 1 + MCP, SQLite + PostgreSQL + real HTTP | **175 passed, 4 skipped, 0 failed**, 259.43s |
| Full host suite | **88 passed, 91 skipped, 0 failed**, 65.04s |
| Final focused Docker protocol/action checks after error/startup refinements | **28 passed, 48 deselected, 0 failed**, 120.44s |
| Final host discovery/stdio checks | **2 passed, 2 PostgreSQL variants skipped**, 10.55s |
| Live HTTP MCP checks, all three configured identities | Passed |
| Documented stdio container client | Passed; current protocol, discovery, structured health result |
| Ruff lint/format and dependency lock consistency | Passed |

The full suite's four skips are SQLite variants of PostgreSQL-only checks:
concurrent action execution, DB-role privileges, concurrent fault activation,
and migration round trip. Their PostgreSQL variants passed. No PostgreSQL cases
were skipped in the Docker suite. Host skips reflect the intentionally absent
host test-DB/live-API configuration and those SQLite-only exclusions.

The final focused run specifically covers the final protocol error distinction,
explicit server discovery, all seven read calls, invalid/oversized arguments,
both stdio variants, every action mapping's observable recovery, and duplicate
request/grant rejection on SQLite and PostgreSQL. It was run after the full
regression suite; counts are reported separately rather than added together.

Negative coverage includes unknown tools, invalid enums/UUIDs/types/extra fields,
cross-service reads, unauthorized writes, body/result size limits, malicious log
instructions and terminal controls, literal SQL-pattern characters, missing/fake/
expired/forged/rebound/stale grants, reused execution IDs and approvals, concurrent
requests, spoofed caller headers, modified/replayed service assertions, rate limits,
downstream connection errors/timeouts/invalid JSON, and noninteractive approval
issuance. The PostgreSQL role test executes an approved MCP action using a role
that cannot issue approvals or delete faults.

An earlier full run had one read timeout because the positive test fixture used a
one-second deadline while the application uses three seconds. The fixture was
aligned with the configured limit, and the full rerun passed. Later startup tests
exposed cold stdio process imports exceeding shorter client deadlines; bounded
startup and read-only/unbuffered child settings were adjusted and retested. Explicit
short-deadline failure tests remain in place. No failed result was relabeled passed.

## Actual runtime security checks

`scripts.verify_gateway_boundaries` checked the running containers and restricted
database role. It verified:

- The MCP container has no database credential, approval key, Stage 1 control
  token, client-token inventory, host bind mount, or Docker socket.
- Both new containers use the unprivileged application user and read-only root
  filesystems. The authorization service uses `opspilot_gateway`.
- That role cannot insert approvals, edit approval signatures, delete faults, or
  create objects in the public schema. Narrow action/audit privileges are explicit.
- The runtime action flag is false; application approval and execution counts
  remain zero. Read and denial events are persisted in the audit table.
- Application records are structured JSON and do not contain generated tokens,
  DB passwords, or signing keys.

The live outage check deliberately stops only this project's authorizer, exercises
the MCP reader, accepts only an explicit `DOWNSTREAM_UNAVAILABLE` or `TIMEOUT` tool
error with no data, and restarts the authorizer. The observed result is retained
in `stage2-live-unavailable.json`; a network timeout is an explicit failure state,
not a healthy observation. Failure to persist a denial while the backend is down
is recorded in local JSON logs. Normal readiness is checked again after recovery.
The observed offline-authorizer result was **TIMEOUT**, with `ok=false`, no data,
and MCP `isError=true`; the authorizer was then restarted successfully.

## Evidence files

All verification artifacts are ignored generated files under `artifacts/`:

- `stage2-docker-tests.xml` / `.log`: complete regression output.
- `stage2-local-tests.xml` / `.log`: host results.
- `stage2-protocol-final.xml` / `.log`: final targeted protocol and recovery checks.
- `stage2-test-summary.json`: counts parsed from the actual JUnit files.
- `stage2-live-mcp.json`: current protocol, tool discovery, and actual live outcomes.
- `stage2-live-unavailable.json`: actual offline-authorizer failure result.
- `stage2-stdio-client.log`: the working documented container client output.
- `stage2-security-verification.json`: container, DB privilege, and secret-log audit.
- `stage2-compose.log`: final healthy startup output.
- `stage2-final-state.json`: recovered readiness and retained fixture state.

## Run, use, and stop

Complete PowerShell setup and SDK examples are in MCP_TOOLS.md. On an initialized
workspace, the main commands are:

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --profile mcp up -d --wait
Invoke-RestMethod http://127.0.0.1:8085/health/ready
.\.venv\Scripts\python.exe -m scripts.verify_mcp
.\.venv\Scripts\python.exe -m scripts.verify_gateway_boundaries
docker compose --profile mcp --profile traffic --profile test down
```

The application data volume is retained by `down` without `--volumes`. The API,
PostgreSQL, MCP server, and authorizer are left available locally after verification;
optional traffic and the disposable test database are stopped. No unrelated
containers or volumes were removed.
The disposable test database's final stop ended with exit code 137 after Docker's
stop grace period. Its temporary test data is disposable; the application database
remained healthy and its persistent volume was untouched. Optional traffic exited 0.

The final boundary audit recorded **24 persisted gateway audit events**, **zero
application approvals/executions**, and **29 valid JSON log records** without any
generated token, password, or key present. Final API/MCP readiness checks passed,
and no active simulated faults or open incidents remained.

## Known limitations

- Local pre-provisioned HTTP tokens are not a complete OAuth login/discovery system.
- Human approval depends on a trusted local operator account and protected admin
  credentials. A terminal prompt alone cannot prove human presence. The interactive
  approval interface was not exercised as a real human action during automation;
  positive execution tests used clearly labeled isolated approval fixtures.
- Rate windows are per process and reset on restart; there is one worker per service.
- There is no TLS, identity-provider integration, automatic key rotation, audit
  retention policy, or distributed enforcement store. This is not public hosting.
- A network-timed-out action may have committed; no automatic retry occurs, and
  execution/grant uniqueness guards against duplicate effects.
- Stage 1 resource models remain per workload; observations are not production
  telemetry or active health probes. No shell/file/cloud/SQL execution tool exists.
- No uncontrolled autonomous agent, LLM integration, deployment, or Stage 3 work
  was performed. Stop after this Stage 2 verification.
