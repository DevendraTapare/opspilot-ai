# Stage 4 verification report

Verification: **2026-11-02–03**, Asia/Calcutta. Workspace: `D:\Projects\OpsPilot-AI`.

## Implemented scope

Durable execution now starts at the handoff of a completed Stage 3 investigation.
The investigation, evidence and exact proposed action are persisted before the
human gate. A real LangGraph graph uses the official PostgreSQL checkpointer,
stable run/thread UUIDs, synchronous checkpoints and durable interrupts. A
separate authenticated interactive human CLI approves/revokes immutable requests.
Models cannot approve themselves or access the execution credential.

The authorization backend independently revalidates the human grant, exact tool
arguments, run, target and current preconditions. Action effect/consumption/ledger
records commit atomically. A coordinator reconciles uncertain results before any
redelivery and performs an approved bounded verification workload. Confirmed
failure requires a fresh investigation/run and a separately signed recovery grant.

No irreversible/production action, cloud deployment, Git commit or push was added.
Stage 1 simulator behavior, Stage 2 legacy approvals and the Stage 3 read-only model
boundary are retained. Stages 1–3 historical reports remain historical records.

## Files and dependencies

New code is in `opspilot/durable/`: typed contracts, immutable policy/fingerprints,
repository/audits, operator authentication/CLI, official PostgreSQL persistence,
scoped MCP executor, backend reconciliation/verification and the durable graph/CLI.
Migration `0003_durable` adds five application tables and two nullable legacy grant
fields. Checkpoint tables live in a dedicated PostgreSQL schema.

New setup/verification scripts: `scripts/initialize_durable.py` and
`scripts/verify_durable_boundaries.py`. Tests are `tests/test_durable.py` and its
guarded subprocess fixture `tests/durable_crash_worker.py`.
Required docs: DURABLE_EXECUTION.md, APPROVAL_SECURITY.md and this report.
The complete authored inventory is FILE_MANIFEST.md.

Updates include schema/readiness, backward-compatible MCP action bindings, two
scoped supervision tools, gateway policy/dispatch, private-file exclusions,
optional test DB loopback port, test-report credential redaction, setup/client
verification and current documentation. Stage 3 investigation code is unchanged.

| Component | Locked/observed version |
|---|---|
| Python host / container | 3.12.3 / 3.12.14 |
| LangGraph | 1.2.19 |
| langgraph-checkpoint-postgres | **3.2.0** |
| Psycopg / psycopg-pool | 3.3.6 / 3.3.3 |
| PostgreSQL | 18.6 |
| MCP SDK / wire protocol | 2.3.0 / 2026-07-28 |
| Pydantic / SQLAlchemy / Alembic | 2.14.2 / 2.0.55 / 1.20.1 |

The lock resolves 78 packages. Official [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
and [interrupt/resume semantics](https://docs.langchain.com/oss/python/langgraph/interrupts)
were checked, including node replay after an interrupt. The official
[PostgreSQL saver documentation](https://pypi.org/project/langgraph-checkpoint-postgres/)
specifies autocommit, dictionary rows and restricted deserialization; the
implementation uses those settings with pickle fallback disabled.

## Demonstrated guarantees

These guarantees apply to the local fictional simulator and its PostgreSQL
transactional action/verification backend, not arbitrary external systems:

| Guarantee | Evidence exercised |
|---|---|
| Approval survives restart and is not inferred from a resume value | Durable interrupt loaded by a new saver/graph/process; forged resume data cannot create a grant |
| Exact action/run binding | Changed tool, service, request UUID or run UUID rejected without an effect |
| Persistent approval integrity | PostgreSQL rejects changed fingerprint/bindings; signed backend grant binds the fingerprint; append-only audit rejects deletion |
| Expiry/revocation/staleness reject execution | Real MCP negative calls; no execution ledger entry or new effect |
| Review-to-execution freshness | Resource changes during human review prevent grant issuance; later changes are rechecked at execution |
| Concurrent resume exclusion | One actual resume pauses before delivery while another receives `RUN_BUSY`; first finishes with one effect |
| Stable idempotency across crashes | Preallocated UUIDv5 action key and immutable argument set reused after restart |
| Atomic observable action effect | Fault deactivation, grant consumption, unique execution, deployment event and durable audit commit together |
| Lost acknowledgment recovery | Fresh process reads the committed ledger and continues to verification without repeating the action |
| No blind retry after unavailable reconciliation | Unknown result interrupts; restored ledger is queried first |
| One observable verification result | Verification workload/metrics/logs/incidents and its unique result commit together; replay reads the stored result |
| Success is not assumed from action completion | Injected payment outage makes verification fail after checkout restart succeeds |
| Recovery needs separate authority | Failed run is linked to a new diagnosis/run; no second action occurs before a new synthetic human grant; approved dependency recovery verifies healthy |

Exactly-once here means **at most one committed observable effect for the approved
action key**, and one committed verification workload/result for that key. With a
valid approval, restored availability and a resumed worker, tested crash cases
eventually completed once. It does not mean every request must succeed, that a
checkpoint alone prevents duplicate effects, or that nontransactional remote
side effects can be rolled back. A database/volume loss is outside the guarantee.

## Failure injection boundaries

- **Worker restart before approval:** child process reads the pending checkpoint
  and hard-exits; a new process still requires an authenticated operator decision.
- **Crash immediately after approval:** hard process exit after the signed grant
  commits and before graph resumption; the grant and interrupt remain durable.
- **Crash just before tool execution:** durable prepared attempt exists; a simulated
  crash leaves the execution node incomplete. Recovery reconciles then delivers
  the same key once when the ledger proves no commit.
- **Crash after tool execution before local acknowledgment:** the actual MCP
  backend transaction commits; the worker hard-exits before recording its receipt.
  A new process recovers the committed result. This is a worker receipt boundary,
  not a claim that a production server was killed mid-transaction.
- **Lost RPC acknowledgment and unavailable downstream:** a test transport loses
  the actual committed response and reconciliation availability; the graph pauses
  and later recovers by reading the real ledger.
- **Verification acknowledgment crash:** a committed measurement result is read
  from its unique ledger after the worker resumes.
- Duplicate request/decision, competing resumes, expiry, revocation, modified
  arguments, stale incident/resource and failed verification are separate cases.

The two hard-exit test processes use `os._exit(91)`: no Python `finally` blocks
close the saver or release the advisory lock. PostgreSQL session cleanup and a
fresh process provide the recovery. The crash helper refuses any database other
than the dedicated test database and a generated test schema. It is not packaged
as a runtime crash API or model tool.

## Verification evidence

The PostgreSQL durability run before the final review-race/self-approval additions
passed **21 tests**, with **20 explicit SQLite skips** (`stage4-durable-tests.xml`,
235.21 seconds). There is no in-memory fallback pretending to establish durability.
A focused run of concurrent resumes, review-time resource changes and separately
approved recovery passed **3 tests**, with **3 SQLite skips**
(`stage4-policy.xml`, 50.93 seconds).

Tests exercise actual TCP MCP discovery/calls and PostgreSQL checkpoints, not
ordinary functions labeled as MCP. Human approval tests authenticate synthetic
operator credentials and mock the terminal/hidden prompt. They do not represent
live human approvals. Investigation decisions use the explicitly labeled Stage 3
fixture model. No real LLM was configured or invoked in Stage 4.

Initial development runs exposed Windows' incompatible default Proactor event loop,
a clock-fixture serialization issue and a subprocess import-path problem. These
were corrected. Transient local connection/deadline failures were retained in
early artifacts. The Stage 4 test gateway uses its supported 10-second bounded
transport profile for cold Windows/Docker testing; the runtime gateway remains
at its existing three-second default and backend SQL/lock deadlines are unchanged.
Generated credentials found in retained failed connection tracebacks were
redacted, and test reporting now redacts those credentials before writing reports.

The actual local database privilege check passed (`stage4-runtime-boundaries.json`):
the runner cannot insert grants, set/insert approver fields, directly update faults,
or delete audit events; the operator cannot change faults or forge execution rows;
the backend cannot insert grants or edit approver identity. Worker configuration
contains no operator token or approval key.

The full Stages 1–4 regression recorded **229 passed, 1 failed, 1 error and
27 skipped** (258 cases, `stage4-regression.xml`, 652.65 seconds). The failure
was an existing MCP pagination case hitting the three-second backend deadline;
the error was an existing schema comparison case failing to connect to PostgreSQL
before comparison. Both unchanged cases passed their focused rerun (**2 passed**,
`stage4-recheck.xml`, 16.26 seconds). The original failures remain recorded;
this is not a clean full-suite result. Its Stage 4 subset had 23 passes and
22 explicit SQLite skips, with no failure/error.

An actual restricted-role CLI smoke check subsequently exposed unnecessary
`SELECT FOR UPDATE` permissions during proposal/signing. Those read-only phases
now revalidate versions without locking services or the legacy grant; the backend
retains its transactional resource locks and final precondition checks. A new
PostgreSQL test runs the complete approved workflow under deliberately restricted
worker/operator roles, with service/fault write privileges absent. No broader
privileges were granted to hide that defect.

The actual host worker now creates a request using `.runner.env` alone:
`stage4-live-pending.json`. It persisted two PostgreSQL checkpoints. An unapproved
resume exited 2 and appended `resume_rejected: APPROVAL_REQUIRED`
(`stage4-live-unapproved-report.json`). At that check the primary database had
one pending request, zero signed grants, zero action executions and zero
verification workloads. No live human approval was simulated in this database.

The live investigation handoff used the fixture model: five real read-only MCP
calls (`get_incident`, `get_service_metrics`, `search_service_logs`,
`get_dependency_status`, `list_recent_deployments`) in 7,266 ms of graph time.
It cited worker saturation and healthy sampled dependencies, proposing only
`restart_simulated_worker` for checkout. Its eleven deterministic fixture
decisions are not real LLM reasoning. Real token usage/cost is unavailable.

The **final Stage 4 suite**, after the restricted-role correction, passed
**24 tests, 23 explicit SQLite skips, zero failures/errors** in 407.42 seconds
(`stage4-durable-final.xml`). This includes the full restricted-role execution,
all crash/restart cases, concurrent resumes, stale/revoked/expired approvals,
modified bindings, immutable audits, lost acknowledgment, failed verification and
separately authorized recovery. `stage4-test-summary.json` records the distinct
runs without erasing their earlier failures. Ruff lint/format and `uv lock --check`
also pass (79 Python files, 78 locked packages).

## Limits

- Durability begins at the completed-investigation handoff; interrupted Stage 3
  LLM calls before that point are not recovered by this execution graph.
- No real-model performance or live human approval session is claimed. Test
  operators and fixture decisions are explicitly synthetic.
- The human boundary trusts the local OS account and private credentials. TTY
  presence is not cryptographic proof of physical human presence; see APPROVAL_SECURITY.
- Session-lock recovery can wait for PostgreSQL to detect a lost connection.
  No lease stealing or distributed failover guarantee is claimed.
- Verification is bounded to the approved load/window. The default baseline can
  recover even when a much larger simultaneous burst still exceeds queue capacity.
- Administrative full audit exports grow with retained events; no pruning or
  enterprise retention service is implemented. MCP result sizes remain bounded.
- No automatic approval, irreversible remediation, production/cloud integration,
  deployment, commit, push or later-stage work is included.

Startup, approval, resume, recovery and stopping commands are in DURABLE_EXECUTION.md.

## Final runtime and outcome

At **2026-11-03 13:54 Asia/Calcutta**, the final rebuilt image was running with
healthy `api`, `mcp`, `authorizer` and `db` containers. API and MCP readiness both
returned HTTP 200. Migration completed successfully at `0003_durable`.
The optional dedicated test database and traffic worker are stopped; no volumes
were deleted. See `artifacts/stage4-final-state.json` and final image/Compose logs.

Sandbox actions remain disabled. The primary database has one pending review
request and two checkpoints, with no signed grants, executions or verification
workloads. That request has a fixed ten-minute TTL and will expire without action;
it cannot be renewed by replay. The intentionally prepared checkout fixture remains
for review. Create a fresh investigation/request if its evidence or approval expires.

The retained Stage 2 live MCP verifier passed after the registry extension.
Runtime log samples parse as structured JSON. An exact local-credential scan of
42 Stage 4 artifacts and the last 100 log lines per runtime application service
found no additional credential exposure (`stage4-secret-scan.json`); this is a
bounded check, not a universal secret-detection guarantee.

**Stage 4 scoped verification: PASS. Overall result: CONDITIONAL**, because the
full regression had two transient connection/deadline failures despite both
unchanged focused reruns passing. The final Stage 4 suite has no failures/errors.
Real-model and live human approval verification remain unavailable/not performed;
neither is represented by deterministic fixtures or synthetic test humans.

Stage 4 is complete. No commit, push, cloud deployment, unrelated project change
or Stage 5 work was performed.
