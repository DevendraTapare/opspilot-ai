# Stage 5 report

Verification date: 2026-11-03, Asia/Calcutta. Workspace: `D:\Projects\OpsPilot-AI`.

## Implementation

Stage 5 adds versioned evaluation recipes, isolated PostgreSQL/TCP MCP runners,
rules and real-provider comparison arms, separately labeled fixture smoke checks,
operational approval/recovery/verification probes, explicit-denominator metrics,
uncertainty estimates, fail-closed release assessment and local OpenTelemetry spans.
Stages 1–4 interfaces, transactional action policy and default disabled actions remain.
No migration or production/irreversible tool was added.

The dataset is 120 structurally distinct recipes in twenty families: calibration
20, development 60 and held-out 40. Generation/checksums, rubric, all twelve metric
denominators, operational-track distinction, limitations and reproduction commands
are in [EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md).

New source: `opspilot/observability.py`, `evaluations/runners/` (contracts, dataset,
environment, subjects, metrics, benchmark, operations and release), three evaluation
test modules, versioned JSONL/manifest files and dataset/report documentation.
Existing workflow/provider/MCP, approval/action/verification and logging modules
receive manual content-free instrumentation. Dependency versions are locked.

## Environment and model disclosure

Host Python 3.12.3 on Windows; real local Docker PostgreSQL 18.6. Evaluation
authorizer and MCP servers run locally over TCP against generated schemas in
`opspilot_stage1_test`. Main runtime uses `opspilot`; its pending approval/fault
fixtures are not benchmark reset targets.
Docker Engine is 29.9.2 with one allocated CPU. Local scheduling and warm-cache
effects are relevant to the measured latency and timing-sensitive regression.

OTel SDK/API 1.45.1 and semantic-conventions package 0.66b1 are locked. Emitted
manual GenAI fields use the documented Development convention snapshot 1.37.0.
LangGraph remains 1.2.19, MCP SDK 2.3.0 and Psycopg 3.3.6. The lock has 80 packages.

No real-provider configuration was found. Per the existing user direction, Stage 5
finishes implementation and reports real-model verification as unavailable. No
paid request or automatic provider selection occurred. A is deterministic rules;
fixture smoke decisions are deterministic graph tests, not LLM reasoning. B/C real
results are explicitly excluded and cannot establish superiority, real token cost
or real-model quality/latency.

## Verification results

| Run | Actual result |
|---|---|
| Initial dataset/denominator/privacy unit checks | 6 passed |
| Protocol/projection/trace-parent recheck | 7 passed, 1 PostgreSQL-only SQLite skip |
| Final scorer and release checks | 7 passed (`artifacts/stage5-score-check.xml`) |
| Broad non-opt-in Stages 1–5 regression with local tracing | **246 passed, 1 failed, 40 skipped**, 287 cases, 628.52 seconds |
| Unchanged isolated failing-case rerun, also tracing enabled | **1 passed**, 3.14 seconds |
| Final operational track | **9 passed, 9 explicit SQLite skips**, 142.62 seconds |

The broad regression's failure was
`tests/test_agent.py::test_wall_clock_budget_cancels_model_without_fallback`:
the existing 100ms total-budget test received `failed` where it expected
`budget_exhausted`. It passed unchanged in isolation with the same tracing opt-in.
The discrepancy is retained, not suppressed or declared conclusively fixed.
It is a remaining timing-sensitive status-classification risk. The 40 skips were
SQLite exclusions for PostgreSQL guarantees, two deliberately disabled main-runtime
live tests and the unconfigured real-model opt-in. Native FastAPI/PostgreSQL and
actual TCP MCP tests still ran. No main fixture reset was needed.

The broad run predates a final evaluation-only scoring correction: invalid-decision
abstentions cannot earn task-completion credit, and a B diagnosis needs both service
and mechanism before being structurally supported. The seven focused checks passed
after that correction. Fresh operational and final diagnostic reports use the same
subsequent source/test/lock/dataset hash; the release report confirms this match.
No agent, gateway or action policy changed with that scoring correction.

An initial integration check found that traceparent validation rejected the SDK's
valid W3C random-trace flag. Validation now accepts standard two-digit trace flags,
and real MCP parentage passed. Early failed and partial artifacts remain separate
from final experiment results. The initial two-case harness smoke is not pooled
into the final benchmark.

## Actual benchmark samples

Each selected arm/case used the same recipe and limits. A executed all **120**
cases through real MCP. B and C each had **120 excluded cases** with
`REAL_MODEL_UNAVAILABLE` (240 exclusions total), **zero attempted real-model cases**.
No excluded case became an abstention, success, zero-latency sample or fixture
substitution. Matched real-model comparisons have sample size zero and `null`
differences/intervals. **No superiority claim is made.**

| Split / A rules baseline | Attempted | Correct root / answerable | Completed tasks / attempted | Abstentions | p95 diagnostic E2E |
|---|---:|---:|---:|---:|---:|
| Calibration | 20 | 11/13 (84.62%) | 17/20 (85.00%) | 6 | 2,219ms |
| Development | 60 | 36/39 (92.31%) | 54/60 (90.00%) | 18 | 2,110ms |
| Final held-out | 40 | **24/26 (92.31%)** | **36/40 (90.00%)** | 12 | **1,719ms** |
| All splits, descriptive aggregate | 120 | 71/78 (91.03%) | 107/120 (89.17%) | 36 | 2,000ms |

A had **zero timeouts and zero failed runs** in these final 120 trials. Its 84
diagnoses include six unsupported diagnoses under the frozen unanswerable-case
rubric. Wrong-but-grounded root labels remain separate correctness errors.
Healthy and inconclusive cases are excluded from root accuracy's denominator,
but remain in task completion and timing denominators.

Final held-out measurements for all requested metric categories:

| Metric | Observed result / denominator |
|---|---|
| Root cause | 24/26; Wilson 95% **75.86–97.86%** |
| Task completion | 36/40; Wilson 95% **76.95–96.04%** |
| Appropriate tool selection | 174/200 calls (87.00%); required-tool coverage 40/40 |
| Unsupported diagnosis | **2/28 diagnoses (7.14%)**, Wilson 95% 1.98–22.65% |
| Unauthorized action attempts | A: 0 observed / 200 diagnostic calls; operational track separately injected 2 attempts in 5 security trials, zero effects |
| Approval bypass | A: no approval decisions, rate `null`; operational: 1 injected bypass attempt in 5 security trials, blocked |
| Duplicate side effects | Diagnostic A: zero state changes; operational: **0 extra effects / 4 replay-or-recovery trials** |
| Restart recovery | Diagnostic track not exercised (`null`); operational: **3/3 hard-process trials**, Wilson 95% 43.85–100% |
| End-to-end latency | A held-out p50 **968ms**, p95 **1,719ms**, 40 attempted cases; bootstrap p50 829–1,062ms, p95 1,265–2,000ms |
| Model tokens / API cost | A: 0 input/output tokens, USD 0 API cost across 40 cases; B/C: unavailable, no attempted inference; compute/energy cost not measured |
| Diagnostic calls | A: **200/40 = 5.0** calls/incident; all splits 600/120 |
| Remediation verification accuracy | Diagnostic track not exercised (`null`); operational: **6/6 judgments**, Wilson 95% 60.97–100% |

These intervals describe a small related simulator suite, not production SLOs.
The all-split aggregate is descriptive and does not replace held-out evaluation.

The explicitly separate structured **fixture smoke** executed six calibration
cases: five diagnoses, one abstention, no timeout/failed run, 35 actual MCP calls.
Its fixed worker rule matched only 3/6 labels; it is deliberately not represented
as genuine model reasoning or a B/C real comparison. No real model name, actual
token usage, real-model latency or API cost estimate is available.

## Operational evidence and gates

The final nine-trial operational report records actual local ledger counts and
verification outcomes. Four expected security denials were correct (4/4), including
authenticated synthetic-human rejection. They count as successful policy behavior.
Three hard-process restart trials completed with one committed effect each; the
duplicate-delivery probe produced no second effect. A successful checkout action
with an induced payment failure was correctly marked failed verification, then a
new independently authorized recovery verified healthy. Those results are six
verification judgments, not six independent production incidents.

All operational gates passed: complete sample, zero unauthorized effects, zero
duplicates, exercised restart recovery and verification accuracy.

**Failed/unavailable gates remain visible:**

- A fails the unsupported-diagnosis gate: **7.14% > 5%** on held-out. Its root/task,
  latency, API-cost and diagnostic-no-effect gates pass; it is a rules control.
- B/C have zero real-model attempts. Correctness, unsupported diagnosis, security
  observation, latency and cost evidence are unavailable, and the minimum real
  sample-size gate fails. Recovery/security infrastructure evidence passes separately.
- The final report has all 40 held-out IDs and matching final source hashes, but
  **`release_ready=false`**. Release CLI exited **1**, as designed for blocked gates.
- The broad regression's one original timing-sensitive failure remains recorded,
  despite its isolated passing rerun.

## Evidence files

Under `evaluations/reports/`:

- `calibration-final.json`, `development-final.json`, `held-out-final.json` and their
  frozen `.plan.json` files: actual final diagnostic trials and explicit exclusions.
- `fixture-smoke-final.json`: clearly separate deterministic graph/readback smoke.
- `operational-final.json`, `.trials.jsonl`, `.xml`, `.log`: final nine operational
  trials and measured ledger observations.
- `regression-and-operations-final.json`, `.xml`, `.log`: retained broad regression;
  its operational subtrack passed, while pytest's overall exit was 1.
- `release-final.json`: matched-source gate assessment; no release/deployment action.
- `stage5-summary.json`: all final split metrics, operational metrics, exclusions,
  confidence intervals and release outcome; early smokes are explicitly excluded.
- PID-suffixed `*.traces.*.jsonl`: local OpenTelemetry traces. Diagnostic trial
  `trace_id` links to client/server/backend spans. Hard-crash unfinished spans may
  be absent; durable action audits/checkpoints remain authoritative.

Focused pytest checks/rechecks and image/Compose/verification logs are in
`artifacts/stage5-*`. Versioned datasets, three test modules and source inventory
are listed in FILE_MANIFEST.md. Historical Stage 1–4 reports are preserved.

## Limits and outcome

- Real model execution and A/B/C superiority are **unverified**, not simulated.
- 120 recipes represent twenty families/five mechanisms, not 120 independent
  fault implementations or production-distribution incidents.
- All diagnostic recipes ran for A. Operational recipe contingencies are covered
  by nine representative probes, not 120 complete human-approved workflows.
- Human identities/TTY input in operational tests are explicitly synthetic. No
  live operator granted a main-database action during this stage.
- Structural grounding and the conservative C mechanism projection are proxies;
  they do not establish semantic correctness of arbitrary model prose.
- Short overall-budget status classification has the retained regression discrepancy.
- Timing includes local tracing and the bounded test gateway; host scheduling,
  warm caches, case-family dependence and small tail samples limit interpretation.
- Real-token billing, cache/reasoning-specific prices, hardware cost, remote collector
  operation and long-term trace retention are not verified.

## Final runtime verification

At **2026-11-03 15:11 Asia/Calcutta**, the final rebuilt image had healthy `api`,
`mcp`, `authorizer` and `db` containers; API/MCP readiness returned HTTP 200.
Migration remained `0003_durable`. The actual container imports SDK 1.45.1,
LangGraph 1.2.19 and MCP 2.3.0. Evaluation datasets are absent from the runtime image.
The optional test DB and traffic worker are stopped. No volume was deleted, and
zero generated test schemas remained before stopping the dedicated test DB.

Restricted runner/operator/backend privilege checks passed. Main data still has
three services, one prior durable run/request and **zero signed grants, executions
or verification workloads**. That prior request is effectively expired; actions
remain disabled. There was no live human approval, automatic execution or main
fixture reset. See `artifacts/stage5-final-state.json`, `stage5-schema-cleanup.json`,
`stage5-runtime-boundaries.log` and image/Compose logs.

The final observability/privacy check parsed **8,213 JSON span records** across
retained Stage 5 evidence, scanned **64 artifacts**, and found zero forbidden
content attributes or exact local credential values requiring further redaction.
Final benchmark/fixture traces contained zero `chat` spans; regression provider
adapter mocks are documented separately. The last 100 log lines per runtime app
service also contained no exact local credential values. This bounded check is not
a universal secret detector. See `artifacts/stage5-observability-check.json`.
Ruff lint/format and the 80-package lock check pass.

**Outcome: CONDITIONAL.** The evaluation/tracing framework and operational checks
work; agent release gates are blocked by unavailable real-model evidence, the
baseline unsupported-diagnosis failure and the retained regression failure.
No fabricated benchmark, automatic approval, main-fixture reset, Git commit/push,
cloud deployment or Stage 6 implementation occurred. Stop after Stage 5 verification.
