# Stage 3 verification report

Date: **2026-11-02**, workspace `D:\Projects\OpsPilot-AI`.

## Verdict: CONDITIONAL — real model unavailable; regression transport timeout

The LangGraph investigation implementation, explicit real-provider adapters,
read-only MCP execution, evidence projection, typed decisions, conservative
recommendation gates, budgets and separate deterministic fixtures are implemented.
Stages 1/2 retain their APIs, simulator behavior, database schema and action controls.
No automatic remediation is implemented.

**No real LLM was used.** No provider configuration was found in the project or
process environment, and neither local Ollama (`11434`) nor LM Studio (`1234`)
responded. The user explicitly selected “Finish implementation and report
real-model verification as unavailable.” No model was downloaded, no paid API was
contacted, and the real smoke test remains opt-in. Deterministic results below
are fixture execution, not genuine LLM reasoning or proof of real-model accuracy.

## Files and technology

New files:

- `opspilot/agent/schemas.py`: bounded Pydantic graph state and structured decisions.
- `workflow.py`: eight LangGraph nodes, conditional evidence loops, deadlines,
  scope/citation checks, root-cause/remediation proposals, and abstention.
- `providers.py`: provider-neutral protocol and real OpenAI-compatible/Ollama
  HTTP adapters; planning function calls and JSON-schema outputs, fixed safe errors.
- `mcp.py`: actual SDK discovery and read-only calls with reader-credential checks.
- `evidence.py`: positive operational-data projection, excluding fixture truth.
- `fixtures.py`: explicitly deterministic fixed-order/threshold test behavior.
- `cli.py`, `__init__.py`: explicit execution modes and retained JSON run artifacts.
- `scripts/verify_agent.py`: separate trusted checkout preparation and isolated
  child-process investigation; no admin/approval/DB credential passed to the graph.
- `tests/test_agent.py`: graph, selection, validation, budgets, failures, unsupported
  hypotheses, provider contract tests, actual MCP integration, opt-in real smoke.
- `docs/AGENT_ARCHITECTURE.md` and this report.

Updated: `pyproject.toml`, `uv.lock`, `.env.example`, README, architecture, security
boundaries, roadmap and file manifest. Exact authored inventory: FILE_MANIFEST.md.
No Stage 1/2 implementation modules, migrations, Compose topology or Dockerfile
were changed. Existing database history is retained.

| Technology | Locked/observed version |
|---|---|
| Python host / Docker | 3.12.3 / 3.12.14 |
| LangGraph | **1.2.19** |
| LangChain Core (transitive) | 1.7.3 |
| MCP SDK / MCP types | 2.3.0 / 2.3.0 |
| MCP wire protocol | 2026-07-28 |
| Pydantic / FastAPI | 2.14.2 / 0.162.0 |
| PostgreSQL / SQLAlchemy | 18.6 / 2.0.55 |
| Alembic / Psycopg | 1.20.1 / 3.3.6 |
| HTTPX2 | 2.16.0 |
| Pytest / Ruff | 9.2.0 / 0.17.3 |

`uv.lock` resolves 76 packages. The graph uses the current documented
[LangGraph state and conditional-edge APIs](https://docs.langchain.com/oss/python/langgraph/graph-api).
Provider adapters follow [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)
and the [official Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md).
Mocked HTTP adapter tests verify request/response contracts; compatibility with a
particular running model is unverified until the real smoke is run.

## Live checkout scenario — fixture model, real MCP and PostgreSQL

The trusted operator harness reset **checkout only**, observed a healthy checkout
baseline, then injected checkout worker saturation and issued a 30-request burst.
The operator-only trigger file was kept separate from model context. The agent
received the incident UUID and a neutral investigation goal, with fixture metadata
removed from every observation.

The final live run completed successfully, using actual official SDK MCP discovery
and tool calls against the Docker services:

| Reference | Tool called | Observed evidence |
|---|---|---|
| `e001` | `get_incident` | Open checkout incident and observation timestamps |
| `e002` | `get_service_metrics` | 30 requests, 27 errors, 90% error rate, 100ms p95, 100% worker utilization, 0% DB-pool utilization |
| `e003` | `search_service_logs` | Five sampled requests returned HTTP 503 |
| `e004` | `get_dependency_status` | Payment and inventory sampled windows healthy |
| `e005` | `list_recent_deployments` | Bounded operational deployment/configuration history without scenario labels |

**Fixture diagnosis:** checkout worker capacity is saturated; sampled dependency
health contradicts the alternative hypothesis of a downstream outage.
**Proposal:** `restart_simulated_worker` for checkout, subject to separate human
review and approval. Compare the same workload's errors and utilization after any
separately authorized execution. Risk: interruption of in-flight work.
Confidence **0.8** is a fixture rule value, not an LLM estimate or calibrated score;
the result explicitly states that one simulated window does not prove causality.

Graph latency: **7,843ms**. Whole child-process latency including imports and MCP
connection/discovery: **23,953ms**. Eleven fixture decision invocations occurred.
There were **no model inference calls**, so token usage and model cost are
not applicable/unavailable, not measured zero-token LLM reasoning.

The five observation request UUIDs match five persisted successful read audits
under `incident-reader`. Runtime approval count and action-execution count both
remain **0**. The checkout fault was still active after investigation, proving the
proposal did not execute. The agent artifact contains no scenario/fault IDs, seeds,
generations or canonical injected-cause labels. A check of 27 application/gateway
JSON log records found no generated secrets.

Evidence: `artifacts/stage3-fixture-investigation.json`, its `.log` and separate
`.trigger.json`, and `artifacts/stage3-live-verification.json`. Retained unsuccessful
attempts are `stage3-startup-attempt.log` and `stage3-downstream-timeout.json/.log`.

## Test evidence

The complete Docker suite finished with **207 passed, 1 failed, 5 skipped**
(213 total, 1,010.02 seconds; `artifacts/stage3-docker-tests.xml/.log`).
All **33 Stage 3 non-smoke cases passed**, including SQLite and PostgreSQL
integration through actual MCP. Its one real-model smoke case was skipped.
The other four skips are SQLite variants of PostgreSQL-only locking, role and
migration checks; their PostgreSQL variants passed.

The single full-suite failure was the existing Stage 2 case
`test_negative_protocol_arguments[sqlite-get_service_metrics-args4-INVALID_ARGUMENTS]`:
the HTTP client raised `ConnectTimeout` while connecting to the test server,
before receiving a validation result. The complete suite is therefore **not a
clean passing run**. Docker reported one vCPU, with transient startup/health-check
timeouts also observed. Gateway security deadlines and existing tests were not
weakened to hide the failure. The exact failed case was rerun unchanged and
**passed** (1 passed, 17.69 seconds; `stage3-timeout-recheck.xml/.log`). This
supports a transient connection failure; it does not erase the original failure
or make the complete suite a clean pass.

The complete host regression run passed **116 tests**, skipped **94**, with no
failures (`artifacts/stage3-local-tests.xml`, 100.05 seconds). Host skips cover
unconfigured dedicated PostgreSQL/live environments, SQLite variants of PG-only
checks, and the opt-in real-model smoke.

After adding empty/stale-evidence and MCP-timeout coverage, the Stage 3 focused
host run passed **31 tests**, skipped **3**, with no failures
(`stage3-agent-local.xml`, 16.52 seconds). Those skips are the two PostgreSQL
integration variants and the explicit real-model smoke. The full host run predates
these three added cases; the focused run includes them.

Covered behaviors include all graph transitions, two alternative diagnostic
orders, structured-output rejection, independent tool/service/incident allowlists,
MCP tool failures and timeouts, model HTTP errors without fixture fallback,
wall-clock/model/tool-call exhaustion, insufficient evidence, contradicted
hypotheses, unknown citations, empty/stale corroboration, duplicate diagnostics,
malicious log content removal, rejection of operator credentials, and no actions.
Both HTTP adapters have contract tests using mocked responses; these are not real
model tests. Actual MCP tests use real TCP servers, official SDK discovery/calls,
real simulator observations and isolated SQL persistence, with a fixture model.

Early test failures exposed a fixture error-code construction mistake and an SDK
task-group exception-wrapping expectation. Both were corrected before the passing
runs. Live startup and downstream timeout attempts were also retained separately;
they returned failures without diagnoses. Readiness is now checked by the operator
harness before fixture mutation. Stage 2 deadlines were not weakened.

## Final Docker and fixture state

API, PostgreSQL, MCP and authorizer containers are **healthy**. Migration exited
0. The optional test database was stopped cleanly with exit 0; traffic is stopped.
No unrelated containers or volumes were removed.

Immediately after the agent run, the injected checkout fault remained active.
Later, the unchanged Stage 1 live regression test explicitly selected/reset its
fixtures and performed its normal cleanup. Final API checks show **no active
faults and no open incidents**, while history and the investigation artifact remain.
Runtime approvals and action executions remain **0**. This cleanup was the trusted
regression harness, not agent remediation. See `artifacts/stage3-final-state.json`.
Ruff lint/format checks and `uv lock --check` passed.

## Running and review

Working PowerShell commands, provider configuration, an existing-incident client,
test commands, and scoped container stopping are in AGENT_ARCHITECTURE.md.

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --profile mcp up -d --build --wait
.\.venv\Scripts\python.exe -m scripts.verify_agent --mode fixture --prepare-checkout
```

The preparation command resets only checkout, creates baseline observations,
injects a checkout fault, and launches a credential-separated investigation.
Fixture mode never calls a model. Real mode requires explicit provider/model
environment variables; there is no automatic fixture substitution.

## Limits and remaining verification

- Real-model diagnosis, latency, token usage and cost are **unavailable**. A real
  model may select different diagnostics, abstain, hit budgets or misdiagnose.
- Confidence is a model estimate, not a calibrated probability. Citation and
  corroboration checks do not prove semantic or causal correctness.
- Fixture mode covers a narrow capacity-related observation pattern. It cannot
  substitute for evaluating all simulator scenarios with a configured model.
- Run state is in memory and optionally written to local JSON. No resumable
  checkpoints, run-history HTTP API, frontend, agent approvals or automatic actions.
- Local inference must support native tool calls and JSON-schema output within
  configured budgets. Cold starts and resource contention can cause bounded errors.
- Full Docker regression verification contains the connection-timeout failure
  described above; the complete run must not be reported as all passing.
- Stage 2's local bearer authentication, per-process rates and loopback-only
  transport limitations remain documented in SECURITY_BOUNDARIES.md.

No other projects were modified. No commit, push, deployment, automatic
remediation or further stage was performed.
