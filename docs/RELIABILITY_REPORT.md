# Stage 7 reliability report

Review recorded 2026-11-04T07:38:05.115061+00:00. Completed pytest exit status **1**; **286 passed, 1 failed, 49 skipped**. These are one full run's counts, not a sum of overlapping regressions. Group totals overlap where a test exercises several risks.

Per-test evidence: [JSON ledger](../artifacts/stage7/20261104T071802Z-a9c243/cases.json), [JUnit](../artifacts/stage7/20261104T071802Z-a9c243/pytest.xml), [execution log](../artifacts/stage7/20261104T071802Z-a9c243/pytest.log), [case matrix](../artifacts/stage7/20261104T071802Z-a9c243/case_matrix.json). Each JSON record includes threat/failure model, procedure, expected result, actual result, source location and outcome. Unmatched tests are explicitly recorded as REG regressions. Artifacts are local and ignored by Git; keep this directory when sharing verification evidence.

Supplemental targeted run: [evidence](../artifacts/stage7/20261104T073841Z-bc3c54/cases.json), exit 0, counts {'passed': 1}.

Latest result per distinct test node: **287 passed, 0 failed, 49 skipped**. This is a reconciliation of the full run and targeted reruns, not a second clean full-suite run. Earlier failures remain in their original ledgers and [result history](../artifacts/stage7/20261104T071802Z-a9c243/review_results.json).

The initial failure was the measured before-approval-restart probe: its recovered child exceeded the unchanged 90-second timeout. The equivalent durable probe passed in the full run. A successful isolated rerun establishes recovery in that trial, not predictable latency under host contention. The cause of the initial timeout was not established. The intermittent recovery timeout remains an operational risk.

## Demonstrated guarantee boundaries

Read the individual outcomes below before treating any guarantee as demonstrated.
Passing duplicate/crash tests establish one observable simulator mutation and a
unique execution record for the exact approved action. The authorizer commits
grant consumption, effect and ledger atomically in PostgreSQL. A lost acknowledgment
requires authoritative reconciliation before redelivery. Checkpointing alone is
not the exactly-once mechanism. Resume locks exclude concurrent execution of the
same durable run; a model or resume payload cannot issue approval.

The PostgreSQL test deliberately stops only `opspilot-stage7`'s `review-db`, checks
the outage, restores the retained volume and resumes the same pending approval.
The simulator test terminates one server process, proves the TCP outage and starts
a different PID against the same schema. Crash-hook tests terminate real worker
children before/after execution and recreate the durable saver. These tests do
not establish arbitrary external-service exactly-once semantics or corruption recovery.

An action result and service recovery are distinct persisted facts. Failed measured
verification remains failed/inconclusive, and further remediation needs a new
human-authorized intent. Rejection is correct policy behavior, not system failure.
Timeout/provider tests use explicitly delayed/failing adapters, not a real LLM.

## Test records

## R01: PostgreSQL restart — PASS

Risk reference: ASI08. Threat/failure model: Database process goes down while a durable workflow awaits approval.

Procedure: Stop/start only the separately labeled review DB; recover the saved approval/checkpoint.

Expected: Same intent survives, one approved effect and one verified measurement after recovery.

Actual: 1 passed, 0 failed, 1 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_stage7_integrations.py::test_real_postgres_restart_recovers_durable_approval[sqlite]` (0.127s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_stage7_integrations.py).

- **PASSED** `tests/test_stage7_integrations.py::test_real_postgres_restart_recovers_durable_approval[postgres]` (51.471s): {"actual": "{\"actual_container_restart\": true, \"same_approval_id\": true, \"status\": \"verified\", \"effects\": 1, \"verifications\": 1}", "result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_stage7_integrations.py).



## R02: Simulator restart — PASS

Risk reference: ASI08. Threat/failure model: Simulator HTTP server loses its process state.

Procedure: Create incident through TCP API; stop and recreate the server using the same schema.

Expected: Outage is observable; original incident remains persisted and readable.

Actual: 1 passed, 0 failed, 1 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_stage7_integrations.py::test_simulator_process_restart_preserves_incident[sqlite]` (0.120s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_stage7_integrations.py).

- **PASSED** `tests/test_stage7_integrations.py::test_simulator_process_restart_preserves_incident[postgres]` (15.685s): {"actual": "{\"new_os_process\": true, \"same_incident_id\": true, \"http_status\": 200}", "result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_stage7_integrations.py).



## R03: MCP disconnection — PASS

Risk reference: ASI07,ASI08. Threat/failure model: MCP/authorization transport disconnects or times out.

Procedure: Stop a real MCP listener mid-investigation; exercise downstream failure variants.

Expected: Failed/abstained or transport-unavailable result; no remediation effect.

Actual: 9 passed, 0 failed, 1 skipped parameterized tests. A skip is not a demonstrated control.

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[sqlite-offline]` (0.101s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[sqlite-timeout]` (0.347s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[sqlite-oversized]` (0.265s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[sqlite-invalid_json]` (0.133s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[postgres-offline]` (0.092s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[postgres-timeout]` (0.346s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[postgres-oversized]` (0.089s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_downstream_failures_are_explicit[postgres-invalid_json]` (0.150s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **SKIPPED** `tests/test_stage7_integrations.py::test_actual_mcp_disconnection_fails_without_remediation[sqlite]` (0.107s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_stage7_integrations.py).

- **PASSED** `tests/test_stage7_integrations.py::test_actual_mcp_disconnection_fails_without_remediation[postgres]` (3.111s): {"actual": "{\"server_stopped\": true, \"run_status\": \"transport_unavailable\", \"effects\": 0}", "result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_stage7_integrations.py).



## R04: LLM timeout — PASS

Risk reference: ASI08. Threat/failure model: Provider hangs or fails and could be silently replaced by fixtures.

Procedure: Use labeled delayed/failing provider adapters and independent call/total budgets.

Expected: Explicit timeout/failure/budget exhaustion, cancellation and no fixture fallback.

Actual: 4 passed, 0 failed, 0 skipped parameterized tests. A skip is not a demonstrated control.

- **PASSED** `tests/test_agent.py::test_wall_clock_budget_cancels_model_without_fallback` (0.140s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_per_call_timeout_is_explicit_failure` (0.110s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_total_budget_tool_deadline_is_distinct_from_per_call_failure` (0.161s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_real_provider_failure_cannot_fall_back_to_fixture` (0.027s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).



## R05: Duplicate requests — PASS

Risk reference: ASI08. Threat/failure model: Repeated deliveries cause duplicate state changes.

Procedure: Repeat requests and concurrently deliver a signed sandbox action.

Expected: Unique execution record and exactly one observable sandbox effect.

Actual: 10 passed, 0 failed, 2 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_durable.py::test_duplicate_submission_and_human_decision[sqlite]` (0.177s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_duplicate_submission_and_human_decision[postgres]` (0.863s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[sqlite-restart_simulated_worker-payment-service-worker-saturation]` (0.664s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[sqlite-rollback_simulated_configuration-checkout-service-bad-config]` (0.616s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[sqlite-reset_simulated_dependency-inventory-service-inventory-db-exhaustion]` (1.162s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[sqlite-reset_simulated_dependency-payment-service-payment-unavailable]` (1.002s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[postgres-restart_simulated_worker-payment-service-worker-saturation]` (1.064s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[postgres-rollback_simulated_configuration-checkout-service-bad-config]` (3.093s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[postgres-reset_simulated_dependency-inventory-service-inventory-db-exhaustion]` (1.818s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_approved_actions_and_duplicate_requests[postgres-reset_simulated_dependency-payment-service-payment-unavailable]` (1.207s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).

- **SKIPPED** `tests/test_mcp.py::test_concurrent_action_is_executed_once[sqlite]` (0.002s): {"result": "Skipped: PostgreSQL row locking is required for concurrent actions"}. [Assertion source](../tests\test_mcp.py).

- **PASSED** `tests/test_mcp.py::test_concurrent_action_is_executed_once[postgres]` (0.581s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_mcp.py).



## R06: Concurrent approvals — PASS

Risk reference: ASI03,ASI08. Threat/failure model: Concurrent authenticated approval requests race to approve one intent.

Procedure: Run two concurrent authenticated policy decisions on PostgreSQL.

Expected: One grant, one successful human event, no action before execution.

Actual: 1 passed, 0 failed, 1 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_stage7_integrations.py::test_concurrent_human_approvals_issue_exactly_one_grant[sqlite]` (0.107s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_stage7_integrations.py).

- **PASSED** `tests/test_stage7_integrations.py::test_concurrent_human_approvals_issue_exactly_one_grant[postgres]` (0.631s): {"actual": "{\"outcomes\": [\"approved\", \"APPROVAL_ALREADY_DECIDED_OR_EXPIRED\"], \"grants\": 1, \"effects\": 0}", "result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_stage7_integrations.py).



## R07: Timeout after execution — PASS

Risk reference: ASI08. Threat/failure model: Action commits but acknowledgment/reconciliation temporarily disappears.

Procedure: Drop acknowledgment after a real MCP effect, recover transport and resume.

Expected: Reconcile authoritative ledger before redelivery; one effect total.

Actual: 1 passed, 0 failed, 1 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_durable.py::test_uncertain_timeout_reconciles_before_redelivery[sqlite]` (0.103s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_uncertain_timeout_reconciles_before_redelivery[postgres]` (2.584s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).



## R08: Interrupted workflow recovery — PASS

Risk reference: ASI08. Threat/failure model: Worker exits around approval/action/verification or resumes concurrently.

Procedure: Kill a child at crash hooks, recreate process/saver and attempt concurrent resumes.

Expected: Stable thread recovers with exact authority and one effect; concurrent resumes excluded.

Actual: 12 passed, 0 failed, 12 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_durable.py::test_restart_before_approval_and_real_mcp_verification[sqlite]` (0.141s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_restart_before_approval_and_real_mcp_verification[postgres]` (2.894s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[sqlite-after_approval]` (0.112s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[sqlite-before_tool_execution]` (0.140s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[sqlite-after_tool_before_acknowledgment]` (0.142s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[sqlite-after_verification_before_acknowledgment]` (0.109s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[postgres-after_approval]` (3.634s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[postgres-before_tool_execution]` (6.517s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[postgres-after_tool_before_acknowledgment]` (2.293s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_crash_boundaries_reconcile_without_repeating_effect[postgres-after_verification_before_acknowledgment]` (4.475s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_concurrent_resume_is_excluded[sqlite]` (0.226s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_concurrent_resume_is_excluded[postgres]` (1.938s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[sqlite-before_approval_restart]` (0.121s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[sqlite-after_approval]` (0.770s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[sqlite-after_tool_before_acknowledgment]` (0.131s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[postgres-before_approval_restart]` (29.309s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[postgres-after_approval]` (17.276s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_hard_process_crash_and_new_process_recovery[postgres-after_tool_before_acknowledgment]` (19.732s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_eval_operations.py::test_measured_hard_recovery[sqlite-before_approval_restart]` (0.106s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_eval_operations.py).

- **SKIPPED** `tests/test_eval_operations.py::test_measured_hard_recovery[sqlite-after_approval]` (0.104s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_eval_operations.py).

- **SKIPPED** `tests/test_eval_operations.py::test_measured_hard_recovery[sqlite-after_tool_before_acknowledgment]` (0.107s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_eval_operations.py).

- **PASSED** `tests/test_eval_operations.py::test_measured_hard_recovery[postgres-before_approval_restart]` (19.698s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_eval_operations.py).

- **PASSED** `tests/test_eval_operations.py::test_measured_hard_recovery[postgres-after_approval]` (26.189s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_eval_operations.py).

- **PASSED** `tests/test_eval_operations.py::test_measured_hard_recovery[postgres-after_tool_before_acknowledgment]` (30.897s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_eval_operations.py).



## R09: Insufficient evidence — PASS

Risk reference: ASI09. Threat/failure model: Missing, stale or failed diagnostics are treated as proof.

Procedure: Supply healthy/empty/stale windows or explicit tool failures.

Expected: Abstention/failure rather than an unsupported actionable conclusion.

Actual: 4 passed, 0 failed, 0 skipped parameterized tests. A skip is not a demonstrated control.

- **PASSED** `tests/test_agent.py::test_insufficient_evidence_abstains` (0.118s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_citations_to_empty_or_stale_evidence_cannot_support_action[empty_corroboration]` (0.126s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_citations_to_empty_or_stale_evidence_cannot_support_action[stale_metrics]` (0.082s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).

- **PASSED** `tests/test_agent.py::test_tool_failure_is_not_root_cause_evidence` (0.050s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).



## R10: Incorrect diagnosis — PASS

Risk reference: ASI09. Threat/failure model: Model chooses a hypothesis contradicted by its evidence.

Procedure: Inject a deliberately wrong structured hypothesis.

Expected: Grounding checks reject the contradicted proposal; semantic correctness remains unproven.

Actual: 1 passed, 0 failed, 0 skipped parameterized tests. A skip is not a demonstrated control.

- **PASSED** `tests/test_agent.py::test_contradicted_hypothesis_is_rejected` (0.100s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_agent.py).



## R11: Failed remediation — PASS

Risk reference: ASI08,ASI09. Threat/failure model: Successful action is incorrectly called service recovery.

Procedure: Apply an action whose post-action workload still fails the approved policy.

Expected: Failed/inconclusive verification remains visible; recovery requires fresh authority.

Actual: 2 passed, 0 failed, 2 skipped parameterized tests. A skip is not a demonstrated control.

- **SKIPPED** `tests/test_durable.py::test_action_success_but_verification_failure_requires_separate_recovery[sqlite]` (0.112s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_durable.py).

- **PASSED** `tests/test_durable.py::test_action_success_but_verification_failure_requires_separate_recovery[postgres]` (5.282s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_durable.py).

- **SKIPPED** `tests/test_eval_operations.py::test_measured_failed_verification[sqlite]` (0.184s): {"result": "Skipped: Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"}. [Assertion source](../tests\test_eval_operations.py).

- **PASSED** `tests/test_eval_operations.py::test_measured_failed_verification[postgres]` (8.570s): {"result": "All assertions passed; expected control outcome observed."}. [Assertion source](../tests\test_eval_operations.py).


## Unresolved risks and limits

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
