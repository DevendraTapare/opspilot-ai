# Stage 7 completion report — CONDITIONAL

Review recorded 2026-11-04T07:38:05.115061+00:00. Completed pytest exit status **1**; **286 passed, 1 failed, 49 skipped**. These are one full run's counts, not a sum of overlapping regressions. Group totals overlap where a test exercises several risks.

Per-test evidence: [JSON ledger](../artifacts/stage7/20261104T071802Z-a9c243/cases.json), [JUnit](../artifacts/stage7/20261104T071802Z-a9c243/pytest.xml), [execution log](../artifacts/stage7/20261104T071802Z-a9c243/pytest.log), [case matrix](../artifacts/stage7/20261104T071802Z-a9c243/case_matrix.json). Each JSON record includes threat/failure model, procedure, expected result, actual result, source location and outcome. Unmatched tests are explicitly recorded as REG regressions. Artifacts are local and ignored by Git; keep this directory when sharing verification evidence.

Supplemental targeted run: [evidence](../artifacts/stage7/20261104T073841Z-bc3c54/cases.json), exit 0, counts {'passed': 1}.

Latest result per distinct test node: **287 passed, 0 failed, 49 skipped**. This is a reconciliation of the full run and targeted reruns, not a second clean full-suite run. Earlier failures remain in their original ledgers and [result history](../artifacts/stage7/20261104T071802Z-a9c243/review_results.json).

The initial failure was the measured before-approval-restart probe: its recovered child exceeded the unchanged 90-second timeout. The equivalent durable probe passed in the full run. A successful isolated rerun establishes recovery in that trial, not predictable latency under host contention. The cause of the initial timeout was not established. The intermittent recovery timeout remains an operational risk.

## Environment and execution

Local Windows PowerShell, Python 3.12.3, Linux Docker PostgreSQL 18.6, dedicated `opspilot-stage7` Compose project at loopback port 56437. Schema revision remains `0004_dashboard`; no migration or dependency upgrade was required. Locked backend and frontend versions remain in `uv.lock` and `frontend/package-lock.json`. Real MCP SDK discovery/calls, TCP HTTP, separate Node and simulator processes, PostgreSQL transactions/checkpoints and controlled worker crashes were exercised. Stage 7 Next checks use actual HTTP, not a browser; historical Stage 6 Chromium evidence is preserved.

**Real model: unavailable/unconfigured.** No paid calls, model tokens, cost or real-model security results are claimed. Deterministic fixtures and adversarial structured decisions are labeled test inputs. Tests gated on unsupported SQLite durability or unconfigured providers remain skipped with their actual reasons in the ledger. Precisely: 46 SQLite variants require PostgreSQL semantics, two opt-in running-main-API tests were unconfigured, and one real-model smoke was not opted in. Isolated simulator HTTP tests did run. A nonzero pytest result or failed case remains visible.

Environment evidence: [package versions and lock digests](../artifacts/stage7/20261104T071802Z-a9c243/environment.json). Frontend TypeScript checking and the production Next build passed after the body-deadline change; [final build log](../artifacts/stage7-frontend-build.log). Final Ruff checks/format validation passed for 128 Python files. The bounded configured-secret scan inspected 39 report/log/browser-JS files and found zero literal/prefix matches; [scope and result](../artifacts/stage7/20261104T071802Z-a9c243/credential_scan.json). This is not a general DLP claim.

Final shutdown stops only the dedicated review database and retains its volume. The existing Stage 1 Compose services remain stopped. See [container status](../artifacts/stage7/20261104T071802Z-a9c243/final_containers.json). No main database was restarted or reset.

## Confirmed findings and fixes

| ID | Confirmed behavior before fix | Fix and regression evidence |
|---|---|---|
| F01 | Schema-valid metrics and dependency identity substitution could produce a fixture recommendation for the wrong evidence resource. Incident substitution was already rejected later in triage. | Bind all parsed observations to requested service/incident and known dependency topology. Three response substitutions are rejected earlier. `agent/evidence.py`, shared `topology.py`. |
| F02 | Rotating a human registry credential left an existing session usable. | Store a credential/account/subject-bound HMAC session digest; use current registry permissions. Old sessions fail closed. `dashboard/security.py`. |
| F03 | Gateway per-chunk timeouts could be extended indefinitely by drip-fed input; dashboard/BFF body reads lacked absolute deadlines. | Absolute five-second body budgets plus existing 16 KiB limits in ASGI and Next BFF. Real unfinished TCP body returns 408. |
| F04 | Genuine MCP audit/request/metric IDs could accompany forged metric quantities in a submitted investigation. | Reconstruct cited positive projections from persisted telemetry before durable handoff; reject EVIDENCE_CONTENT_MISMATCH. `durable/evidence.py` and `durable/repository.py`. |

Reproduction evidence was retained: `artifacts/stage7-boundaries-before.xml` has
5 failures and 1 skip; `artifacts/stage7-attestation-before.xml` has 1 failure and
1 skip. Focused important-fix regressions: evidence binding 35 passed/3 skipped/
3 deselected; sessions 13 passed/10 skipped/1 deselected; body deadlines 14 passed/
10 skipped; durable attestation and integrations 33 passed/32 skipped. These
overlapping runs are not added to the completed regression total above.
The first integration attempt retained 12 passed/8 skipped/2 failures: offline
socket exception classification and SDK grouped transport errors required explicit
test expectations. Neither failure was silently counted as a successful final
recommendation. A later simulator test was strengthened to restart an OS process.

No action allowlist, approval authentication, database role, expiry, fingerprint,
quota or verification threshold was relaxed. No automatic recovery action was added.

## Deliverables

- Security/reliability documents above and this Stage 7 report.
- Shared topology, response-resource binding, credential-bound sessions, absolute request-body deadlines and persisted fact attestation.
- Three Stage 7 test modules, private Compose fixture, review initialization/runner, case catalog, evidence plugin, report generator and isolated simulator child.
- Machine-readable per-test ledger, JUnit, logs and case matrix in the cited preserved run directory; all earlier reports retained.

## Reproduce in Windows PowerShell

Prerequisites: running Docker Desktop with Linux containers, the existing locked
Python environment and frontend npm dependencies. Run from this project only.
The runner validates Compose labels and the private port before allowing restart.
It creates fresh per-test UUID schemas and removes only those schemas. It never
resets the main database or deletes previous reports.

```powershell
Set-Location D:\Projects\OpsPilot-AI
.\.venv\Scripts\python.exe -m scripts.initialize_stage7
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --wait review-db
Push-Location frontend
npm.cmd run typecheck
npm.cmd run build
Pop-Location
.\.venv\Scripts\python.exe -m scripts.review_stage7
# Use the actual new directory printed by the runner:
.\.venv\Scripts\python.exe -m reviews.stage7_report artifacts/stage7/<run-directory>/cases.json
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
docker compose --env-file .stage7.env -f compose.stage7.yaml ps -a
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

`--focused` runs only the new Stage 7 cases, preserving a new evidence directory.
Review credentials are generated privately in ignored `.stage7.env`, never echoed.
Do not replace the review URL with the main database. Do not run `down -v`, global
container cleanup or test containers from other projects. The review volume stays
retained after stopping. Test listeners and Node processes are owned by fixtures.

## Remaining risks

- No real LLM is configured. Injection tests use real persisted logs/MCP and labeled deterministic or malicious structured model decisions. Semantic resistance to prompt injection, persuasion, plausible incorrect diagnoses and goal hijacking remains **unverified**.
- Positive context projections remove tested log payload fields and fixture truth, but other allowed text remains untrusted. Schemas, system instructions and citation checks do not prove general prompt-injection immunity or causal correctness.
- The telemetry handoff compares cited projected facts with stored simulator rows. It does not prove completeness of an investigation or correctness of model prose. A trusted database owner can alter source rows.
- Local OS accounts, database owners, signing keys and credential files are trusted. No MFA, remote TLS, hostile-tenant isolation, production credentials or independent remote approval service is claimed. Dashboard read views are local service-wide views.
- Session rotation fails closed, including legacy sessions, and requires login again. Rotation does not retroactively revoke previously issued exact action grants; their explicit revocation and expiration remain separate controls.
- Rate counters are per process. Slow-body deadlines do not establish resistance to slow headers, many concurrent sockets, volumetric traffic or CPU/memory exhaustion. Telemetry/session retention needs an explicit maintenance policy.
- MCP SDK HTTP transport failures can propagate as an exception group before a final recommendation is produced. The disconnection test accepts only HTTP transport exceptions and verifies zero action effects; uninterrupted recommendation availability is not guaranteed.
- PostgreSQL restart uses graceful stop/start of the dedicated retained review volume while awaiting approval. WAL corruption, failover replicas and database termination mid-commit are not tested. Simulator restart uses two actual OS processes; worker crash tests use real child exits.
- Exactly-once evidence is limited to transactional simulator effects and their unique action ledger. It is not a guarantee for arbitrary remote side effects. Investigation restarts are marked interrupted; a single dashboard job manager is supported.
- Database role/trigger tests do not protect against a database administrator. Denied HTTP operations are not all durable audit events; action attempts and authoritative transitions have the tested audit path. Independent off-host audit sealing and retention are absent.
- Locked dependencies and an enforced tool inventory are partial supply-chain controls. This review is not an independent CVE, package provenance or model-weight audit. There is one investigator, not a hostile multi-agent network.

## Disposition

**CONDITIONAL**: latest per-node results have no failing assertions; the initial full-run recovery timeout remains an unresolved operational risk. Real-model adversarial resistance and the scope limits above remain unverified. No Git commit/push, cloud deployment or Stage 8 work. Stop at Stage 7.
