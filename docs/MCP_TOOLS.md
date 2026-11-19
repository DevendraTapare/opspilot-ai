# Stage 2 MCP tools

Stage 4 retains the seven-read and legacy three-action profiles below. A separate
`durable-executor` profile adds `get_action_execution` and
`verify_simulated_remediation`, and uses exact `run_id`/`action_fingerprint`
bindings on actions. It cannot use legacy unbound grants. See
[DURABLE_EXECUTION.md](DURABLE_EXECUTION.md) for the new contracts and clients.
The Stage 3 model-facing profile still exposes exactly seven read tools.

OpsPilot exposes real MCP `server/discover`, `tools/list`, and `tools/call` through
the official **MCP Python SDK 2.3.0**, locked with `mcp-types` 2.3.0 in `uv.lock`.
The client explicitly selects **`2026-07-28`**, the
[current protocol revision](https://modelcontextprotocol.io/specification/2026-07-28).
SDK serialization supplies the required per-request metadata. Tools have typed
JSON Schema inputs/output schemas and return MCP `structuredContent`, matching
JSON text content, and an accurate `isError` flag. They are registered on the SDK's
[low-level protocol server](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/),
not exposed as ordinary Python-function calls.

## Start on Windows PowerShell

Run from `D:\Projects\OpsPilot-AI`. Python 3.12, uv, and Docker Desktop with Linux
containers are required. Stage 1's database volume and endpoints are preserved.

```powershell
Set-Location D:\Projects\OpsPilot-AI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-Local.ps1
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
uv sync --locked --python 'C:\Program Files\Python312\python.exe'
.\.venv\Scripts\python.exe -m scripts.initialize_gateway

# Applies 0002_gateway using the existing one-shot migration service.
docker compose up -d --build --wait

# Creates the fixed, limited local DB role; prints no passwords.
.\.venv\Scripts\python.exe -m scripts.provision_gateway_db
docker compose --profile mcp up -d --wait

Invoke-RestMethod http://127.0.0.1:8085/health/ready
docker compose --profile mcp ps -a
```

The MCP HTTP endpoint is `http://127.0.0.1:8085/mcp`. The authorization service
has no host port. Both containers are unprivileged, use read-only root filesystems,
and have no host-directory or Docker-socket mounts. Actions default to disabled.
The initializer is idempotent and preserves Stage 1 credentials.

## Caller profiles

| Local identity | Service scope | Tools |
|---|---|---|
| `incident-reader` | All three fictional services | Seven read tools |
| `checkout-observer` | checkout only | Seven read tool definitions; dependency details require additional scopes |
| `sandbox-operator` | All three fictional services | Seven reads and three approval-gated actions |

Every HTTP request must carry the caller's bearer credential. The registry stores
SHA-256 token digests, not client tokens. Identity comes from the credential, not
tool arguments, JSON-RPC IDs, clientInfo, arbitrary headers, or model text.
Discovery lists only the caller's tool permissions. Service scoping is enforced
again on every call by the authorization backend.

## Input and output contracts

Every tool requires `service_name`: `checkout-service`, `payment-service`, or
`inventory-service`. Inputs reject extra fields, stringified integers, unknown
services, invalid UUIDs, and oversized values. No input accepts URLs, paths,
commands, SQL, Cypher, arbitrary configuration, or approval booleans.

| Tool | Additional input | Structured data |
|---|---|---|
| `list_incidents` | `status`: open/resolved/null; bounded `limit`, `offset` | Incident page, newest first |
| `get_incident` | `incident_id`: UUID; `event_limit` | Scoped incident and bounded recent events |
| `get_service_health` | None | Latest observation, observed time, active fault, healthy/degraded/unknown |
| `get_service_metrics` | `limit`, `offset` | Metric page, newest first |
| `search_service_logs` | Literal substring `query` ≤128 characters; INFO/ERROR/null `level`; pagination | Matching log page, newest first |
| `list_recent_deployments` | `limit`, `offset` | Deployment events with allowlisted configuration fields |
| `get_dependency_status` | None | Fixed topology's direct dependency observations |
| `restart_simulated_worker` | `approval_id`: UUID; `request_id`: UUID | Clears only the approved worker-saturation fault |
| `rollback_simulated_configuration` | Same action inputs | Clears only the approved bad-config fault and records rollback |
| `reset_simulated_dependency` | Same action inputs | Clears only the approved payment-unavailable or inventory-db-exhaustion fault |

Action `approval_id` can be omitted only to receive the explicit approval-required
error. A UUID by itself confers no authority. Worker restart does not run a host
command or restart a container. It restores modeled worker capacity on the next
workload by deactivating the matching fault. Actions do not reset seeds, cursors,
unrelated faults, or other services. Existing incidents require a healthy workload
observation to recover, following Stage 1 behavior.

Pagination defaults to 10, allows 1–20 results, and bounds offsets at 10000.
Incident event limits are 1–20. Pages return `next_offset` or null. Tool arguments
are limited to 4096 serialized bytes; HTTP bodies to 16384 bytes; serialized
structured results to 32768 bytes. MCP also returns a JSON text copy, so the wire
envelope can be larger. Strings from observations are bounded to 256 characters,
with terminal control characters removed. Tool discovery has a fixed upper bound
of ten definitions. Health is an observation, not an active probe; newly injected
faults without subsequent measurements can yield `unknown`.

All results use this shape (abbreviated example):

```json
{
  "ok": true,
  "request_id": "9d8483f3-21a8-4180-9d07-c1571730ec58",
  "data": {"items": [], "next_offset": null},
  "error": null,
  "source": "opspilot-simulator",
  "untrusted_data": true
}
```

Registered tool failures have `ok=false`, `data=null`, a typed `error` containing `code`, a fixed
message, and `retryable`, and MCP `isError=true`. Codes include `UNKNOWN_TOOL`,
`INVALID_ARGUMENTS`, `FORBIDDEN`, `NOT_FOUND`, `RATE_LIMITED`, `ACTIONS_DISABLED`,
`APPROVAL_REQUIRED`, `APPROVAL_INVALID`, `APPROVAL_EXPIRED`, `APPROVAL_USED`,
`DUPLICATE_REQUEST`, `STALE_APPROVAL`, `DOWNSTREAM_UNAVAILABLE`, `TIMEOUT`, and
`RESULT_TOO_LARGE`. Transport failures can return HTTP 401, 405, 408, 413, or 421.
Unknown tool names produce a JSON-RPC `-32602` protocol error with bounded
`UNKNOWN_TOOL` data, following the current specification's error distinction.

## Working SDK client examples

Load only the selected client's credential into the launcher environment:

```powershell
$opspilotReader = Get-Content .env | Where-Object { $_.StartsWith('OPSPILOT_MCP_READER_TOKEN=') }
$env:OPSPILOT_MCP_TOKEN = $opspilotReader.Split('=', 2)[1]

# Genuine MCP discovery followed by a tool call over Streamable HTTP.
.\.venv\Scripts\python.exe -m scripts.mcp_client --tool get_service_health --service checkout-service
.\.venv\Scripts\python.exe -m scripts.mcp_client --tool list_incidents --service payment-service --limit 5
.\.venv\Scripts\python.exe -m scripts.mcp_client --tool search_service_logs --service payment-service --query unavailable --limit 5

# Genuine MCP discovery/call over stdio; both SDK peers run inside the isolated container.
.\.venv\Scripts\python.exe -m scripts.mcp_client --transport stdio --tool get_dependency_status --service checkout-service
Remove-Item Env:\OPSPILOT_MCP_TOKEN
```

The stdio helper runs both SDK peers inside Linux with a fixed Docker command,
passes the credential through the environment, and never interpolates it into
command arguments. This avoids using Windows Docker-exec pipes as the MCP wire.
The server writes
only MCP protocol messages to stdout; JSON audit logging goes to stderr. The
stdio SDK client selects the current protocol and allows thirty seconds for cold
process startup; backend tool deadlines remain three seconds. The
SDK's [client interface](https://py.sdk.modelcontextprotocol.io/client/) also
supports using the transport directly:

```python
import asyncio
import os
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + os.environ["OPSPILOT_MCP_TOKEN"]},
            trust_env=False,
            timeout=15,
        ) as http,
        Client(
            streamable_http_client("http://127.0.0.1:8085/mcp", http_client=http),
            mode="2026-07-28",
            read_timeout_seconds=15,
        ) as client,
    ):
        print((await client.list_tools()).tools)
        result = await client.call_tool(
            "get_service_metrics",
            {
                "service_name": "checkout-service",
                "limit": 5,
            },
        )
        print(result.structured_content)


asyncio.run(main())
```

## Human-approved action workflow

This workflow is for a human operator in their own terminal. An LLM or MCP caller
must never run it to approve itself. Leave actions disabled for observation-only use.

1. The operator inspects the incident and the current fault UUID using Stage 1's
   admin interface. Only the three explicitly modeled remediation mappings are accepted.
2. The operator changes `OPSPILOT_GATEWAY_ACTIONS_ENABLED=true` in local `.env` and
   recreates only `authorizer` with `docker compose --profile mcp up -d --no-deps authorizer`.
   Enabling this flag alone still authorizes no action.
3. The operator runs this command in a real interactive terminal, replacing the
   fault UUID with the one they reviewed:

```powershell
.\.venv\Scripts\python.exe -m opspilot.gateway.approve --caller sandbox-operator --action restart_simulated_worker --service payment-service --fault-id YOUR-FAULT-UUID --ttl 120
```

The command displays caller, action, service, fault, and expiry, then requires the
exact displayed confirmation phrase. It refuses redirected stdin/stdout, has no
`--yes` option, and rechecks the fault after confirmation. It uses the trusted local
operator's admin DB credential to insert a signed approval and a `human_approved`
audit event. Neither server has an approval-issuance endpoint; the authorization
service's database role cannot insert grants.

4. An authorized client may now reference that approval ID, with a fresh execution
   request UUID. Export the operator client credential as `OPSPILOT_MCP_TOKEN`, then:

```powershell
.\.venv\Scripts\python.exe -m scripts.mcp_client --tool restart_simulated_worker --service payment-service --approval-id YOUR-APPROVAL-UUID --request-id YOUR-REQUEST-UUID
```

Grants expire in 30–600 seconds, default 120, and bind the exact caller, action,
service, and fault instance. A grant is consumed once. Duplicate execution IDs are
rejected, and a new request ID cannot reuse a consumed grant. Do not automatically
retry timed-out actions with fresh IDs: a transaction may already have committed.
Restore the action flag to false after operator use and recreate `authorizer`.

## Stage 6 dashboard boundary

The dashboard displays the real registry and invokes investigations through actual
MCP clients. Human approval is a separate authenticated loopback HTTP API behind
the Next.js BFF, never an MCP tool. Models retain only seven read-only tools.
Approved execution reuses Stage 4's separate executor identity, exact fingerprint,
PostgreSQL action ledger and reconciliation. See [frontend architecture](FRONTEND_ARCHITECTURE.md).

## Verification and stop

```powershell
docker compose --profile test run --build --rm tests pytest -q --junitxml=/artifacts/stage2-docker-tests.xml
.\.venv\Scripts\python.exe -m scripts.verify_mcp
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
docker compose --profile mcp --profile traffic --profile test down
```

`verify_mcp` is read-only and requires an existing checkout incident to exercise
`get_incident`; Stage 1's scenario/live tests create such history. The full suite
uses dedicated test databases and synthetic approval fixtures, never grants in
the running application database. See [STAGE_2_REPORT.md](STAGE_2_REPORT.md) for
actual executed results and [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md) for
the trust model and HTTP authorization compatibility limits.
