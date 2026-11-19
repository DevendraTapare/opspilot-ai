# Stage 9E.1 — Token budgets and termination

Date: 19 November 2026. Offline analysis and bounded workflow changes only.
**CONDITIONAL: offline controls verified; real-model completion and Stage 9F remain gated.**
No provider request, credential loading for inference, or real remediation was performed.
Security regressions exercise authorized synthetic sandbox actions only; no existing
user incident or production resource is remediated.
Environment: Windows, Python 3.12.3, LangGraph 1.2.19, Pydantic 2.14.2, MCP SDK
2.3.0, Pytest 9.2.0, httpx2 2.16.0 and Ruff 0.17.3. PostgreSQL integration used the
existing isolated `postgres:18.6-bookworm` review container. No dependencies changed.

## Findings

The [historical ledger](../evaluations/reports/stage9e/20261119T045601Z-b7d83b/requests.json),
[diagnostics](../evaluations/reports/stage9e/20261119T045601Z-b7d83b/model-diagnostics.json)
and [saved state](../evaluations/reports/stage9e/20261119T045601Z-b7d83b/state.json)
show five distinct model-selected diagnostics after an automatic incident read.
There were **no exact duplicate tool calls**. The fifth selection, health, returned
the same metric sample already present in e002. Distinct endpoint names did not
guarantee new independent evidence.

The five assessments all routed to `investigate`. Only the last assessment body
survived; its hypotheses cite only e002 and cannot satisfy the unchanged independent
corroboration check for a final diagnosis. It describes deployment history as missing
despite e005 being available. This supports adding explicit evidence/budget guidance,
but does not prove an LLM prompting fix or a correct final diagnosis.

The finalization route is reachable: `propose` routes to root cause, then remediation
planning. Explicit `abstain` routes to final output. Existing and new fixture tests
exercise both paths. No unreachable node or accidentally unconditional loop was found.
The investigation was already bounded by 14 model calls, eight tool calls and time;
it failed before those limits on the provider error. It was not an infinite execution.

Confirmed contributors to unnecessary consumption were:

- Planning duplicated full validated observations in function-result messages and
  the user context. The schema also appeared in both user text and tool/response
  declarations; hypotheses appeared twice in the assessment context.
- Every `investigate` decision added a planning/assessment pair. The workflow had
  no smaller configurable round limit and did not reserve two decisions for final
  cause/remediation validation before starting another pair.
- The model was not shown its remaining model/round/token budgets. The last
  assessment failed to use all already available evidence.
- Reset-based pacing reduces rolling quota pressure but cannot make an individually
  oversized request fit a quota. Original per-request schema/byte bounds were not
  cumulative token-admission controls.

## Twelve-request analysis

`Est.` uses the stage's conservative estimator: serialized UTF8 JSON byte-equivalents
plus a 512-unit framing reserve. Historical estimates are recovered from the
recorded cost reservation using the original prices and 1,600-output-token cap.
They are **not tokenizer counts or reported usage**. Actual usage is shown separately;
the rejected request's input/output usage remains unknown. No missing value is zeroed.

| # | Workflow state | Selected tool | Est. input units | Reported input | Reported output | HTTP | Exchange ms | Decision | New evidence following decision |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | triage | — | 4,873 | 979 | 187 | 200 | 703 | triage | e001 was read before this request |
| 2 | planning | metrics | 6,751 | 1,256 | 223 | 200 | 563 | select tool | e002 |
| 3 | assessment | — | 9,281 | 2,185 | 661 | 200 | 1,219 | investigate | none |
| 4 | planning | logs | 11,300 | 2,511 | 218 | 200 | 672 | select tool | e003 |
| 5 | assessment | — | 14,148 | 3,865 | 426 | 200 | 2,421 | investigate | none |
| 6 | planning | dependencies | 18,725 | 5,350 | 224 | 200 | 828 | select tool | e004 |
| 7 | assessment | — | 15,707 | 4,377 | 632 | 200 | 1,344 | investigate | none |
| 8 | planning | deployments | 22,648 | 6,481 | 238 | 200 | 1,109 | select tool | e005 |
| 9 | assessment | — | 16,525 | 4,605 | 973 | 200 | 4,110 | investigate | none |
| 10 | planning | health | 24,314 | 6,894 | 440 | 200 | 1,516 | select tool | e006, same metric ID as e002 |
| 11 | assessment | — | 17,503 | 4,939 | 955 | 200 | 2,437 | investigate | none |
| 12 | planning | none accepted | 26,813 | unknown | unknown | 413 | 79 | no decision | none |

Exact tool names are `get_service_metrics`, `search_service_logs`,
`get_dependency_status`, `list_recent_deployments`, `get_service_health`.
All requests after #1 repeated existing evidence; planning repeated it in two
places. The authoritative registry grew monotonically, with no dropped observations.
The [machine-readable replay analysis](../evaluations/reports/stage9e1/20261119T053707Z-35d6b0/replay.json)
records evidence IDs, repetition, decisions, estimates and stopping checks per request.

Abstention was available at every assessment. At #3 only metrics supplemented the
incident, so independent corroboration was missing. From #5 onward metrics and logs
provided inputs that pass the mechanical corroboration test; #7 also had healthy
dependency samples. This made considering a proposal reasonable, not automatically
correct: earlier confidence, explanations and hypothesis citations were not saved.
We cannot establish that #5/#7/#9 could legally finalize under every validation gate.
At #11 the surviving hypotheses cite only one observation. Finalizing that exact
assessment would fail; an explicit abstention was available. No forced diagnosis
or inferred ground-truth answer is used in the new stopping rule.

Known totals remain **43,442 input and 5,177 output tokens**, including 3,342 reasoning
tokens within output. Workflow time was **394.219 s**; ledger exchange latencies sum
to **17.001 s**. The remaining 377.218 s includes pacing, MCP and local orchestration;
the old trace cannot assign exact durations to each. These are historical figures,
not post-change latency or cost measurements.

## HTTP 413 assessment

The failed request had no strict response format: it was a tool-enabled planning
request with `stream=false`. Metadata records `rate_limit_exceeded`, type `tokens`,
request ID `req_01m7s2z4xte84s2grx6jrp8bq3`, and:

- Token limit 8,000; remaining tokens 8,000; reset `1ms`.
- Request limit 1,000; remaining requests 989; reset `15m50.4s`.
- `Retry-After: 5`; no finish reason or token usage.

The [official rate-limit guide](https://console.groq.com/docs/rate-limits) labels
token headers TPM and request headers RPD. Its ordinary rate-limit response is 429;
the [error guide](https://console.groq.com/docs/errors) describes 413 as an oversized
request body. The observed 413 token error is a provider admission rejection, with
individual request size against TPM strongly suggested by the full remaining balance.
The raw message/requested token count was intentionally not retained. The exact
distinction between byte-body limits, per-request token admission and another quota
calculation is therefore **unresolved**. Waiting alone cannot resolve a request
that is individually too large.

Context accumulation is measurable, but not proof of a particular server threshold.
The last reserve implies 26,301 serialized JSON bytes before its 512-unit reserve,
below the local 65,000-unit ceiling. No provider byte limit was recorded. The
[model page](https://console.groq.com/docs/model/openai/gpt-oss-20b) lists 131,072
context tokens and 65,536 maximum output tokens; these are separate from account
quotas. Requests consistently capped output at 1,600. No `length` completion occurred
on successful responses; the 413 response has no completion evidence. Neither
output exhaustion nor exhaustion of the advertised model context is established.
The historical full-schema HTTP 400 remains unresolved and was not retested.

## Implemented controls

`RunRequest` retains configurable `max_model_calls` (default 14, cap 24),
`max_tool_calls` (default 8, cap 12), `max_seconds` (default 180, cap 600), and
per-call timeout (default 30 s). It adds:

| Setting | Default | Valid range | Behavior |
| --- | ---: | --- | --- |
| `max_investigation_rounds` | 4 | 1–10 | Stop after that many assessments if the model still requests investigation |
| `max_estimated_tokens` | 160,000 | 1–1,000,000 | Cumulative pre-dispatch input estimate plus 1,600 output reservation per decision |
| `max_prompt_estimated_tokens` | 32,000 | 1–65,000 | Reject an individually over-budget request before dispatch |

The real HTTP adapter estimates the exact validated envelope it will send. Fixture
or custom providers without an estimator use a documented context/schema byte
estimate; it is not a measurement of their unseen HTTP framing. Reservations are
kept on failures, usage counters remain separate, and unknown reported usage remains
unknown. Estimates are conservative admission accounting, not a tokenizer or an
organization-wide quota guarantee. A smaller operator-selected prompt ceiling can
fail safely even when the provider might have accepted the request.

Before another investigation pair starts, at least four model decisions must remain:
planning, assessment, root cause and remediation planning. If not, return an explicit
incomplete `budget_exhausted` result. This reserves room without compelling a proposal.
When the round cap is reached, a supported `propose` can still follow the existing
validation route; `investigate` stops incomplete and explicit `abstain` remains valid.
All incomplete paths clear root cause/remediation and cannot execute actions.

Exact duplicate tool+argument calls were already rejected before MCP dispatch;
that defense is retained and regression-tested. Different queries/pages/services
are not indiscriminately blocked. Health is not skipped merely because metrics were
read: a new health response could refer to a newer sample. The measured redundant
sample is reported rather than guessed before calling.

## Context and evidence preservation

Planning still reconstructs and validates each original model-call ID, exact
arguments, resource, MCP request ID and observation binding. Successful protocol
results now carry `evidence_ref` and request ID; their full observation appears once
in the request's authoritative observation list. The separate inventory remains.
Every observation's complete positively projected data, timestamps, metrics, request
records and configuration stays intact. No LLM summary replaces evidence, and no
selected competing-hypothesis evidence is omitted to fit a prompt.

The schema appears once in its authoritative tool/response declaration, not again
in user text. Exactly equal hypothesis copies appear once beside assessment metadata;
if they differ, both are retained. Structured
decisions remain tool-free. Historical `SYSTEM` and isolation-probe requests remain
reproducible; new workflow guidance uses `WORKFLOW_SYSTEM` and shows remaining budgets.
No output schema, citation requirement, freshness/corroboration predicate, authorization,
human approval, transaction or idempotency policy was relaxed.

## Offline replay and before/after

The pre-change source was preserved in
`artifacts/stage9e1/20261119T051606Z/baseline/` before edits. Replay uses that workflow
and HTTP adapter against the same saved projected evidence and recorded selections,
with **MockTransport only**, synthetic non-secret credentials and no external calls.
The first four assessment bodies are unavailable; explicit placeholders reproduce
their known `investigate` transitions. The final assessment and triage are retained
outputs. This is a **control-flow fixture replay**, not faithful missing-LLM prose,
a fresh model evaluation, or an MCP protocol replay. Real MCP is covered separately.

| Measure | Before, offline replay | After, offline replay |
| --- | ---: | ---: |
| Mock model requests | 12 | 9 |
| Restored tool reads | 6 | 5 |
| Exact duplicate tool calls | 0 | 0 |
| Serialized prompt bytes, entire run | 174,607 | 90,225 |
| Conservative estimated input units | 182,684 | 96,163 |
| Matched first-nine-request bytes | 109,842 | 90,225 |
| Final status | failed, simulated historical HTTP 413 | budget_exhausted, round limit |
| Accepted diagnosis / remediation | 0 / 0 | 0 / 0 |
| Explicit model abstention | no | no; explicit incomplete instead |
| Validation failures | 0 | 0 |
| Real provider requests / MCP calls / spend | 0 / 0 / $0 | 0 / 0 / $0 |

Matched-prefix bytes decreased **17.86%** under equivalent reconstructed decisions
and evidence. Total-run reduction also includes earlier stopping and must not be
attributed entirely to compaction. The new run retains all five observations it
obtained, byte-identical by canonical hashes; the historical sixth remains preserved
in the immutable original trace. All matched request evidence hashes are identical.
There is no claim of improved real token use, diagnosis accuracy or completion rate.
Fixtures separately verify successful finalization and explicit insufficient-evidence
abstention. The new round limit can reduce completion on harder cases; calibration
with a real model is required before claiming a quality improvement.

Reproduce locally, without a provider key:

```powershell
.\.venv\Scripts\python.exe -m scripts.replay_stage9e1 --baseline-dir artifacts/stage9e1/20261119T051606Z/baseline
```

Each replay creates a fresh report directory. Preserve the baseline artifact directory
with the report when sharing this experiment; it is required for source-snapshot replay.
Earlier replay experiments are retained, including the first run before the shorter
placeholder wording was finalized.

## Files changed

- `opspilot/agent/budgets.py`: new pure offline estimator/output reservation.
- `opspilot/agent/schemas.py`: bounded request settings and separate estimated usage.
- `opspilot/agent/workflow.py`: admission, round stopping, finalization reserve and budget context.
- `opspilot/agent/providers.py`: shared validated envelope builder, pure estimate,
  single-copy schema/evidence transfer and versioned workflow guidance.
- `opspilot/agent/conversation.py`: optional reference-only, provenance-checked protocol results.
- `scripts/replay_stage9e1.py`: offline historical analysis and source-snapshot replay.
- `tests/test_stage9e1_budgets.py`: new budget, termination, provenance and history checks.
- `tests/test_stage9b_pipeline.py`, `tests/test_groq_contracts.py`: updated wire-shape
  assertions that preserve exact binding and trusted-schema guarantees.
- This report and additive evaluation/artifact records. No dependency or default-model change.

## Regression results

Completed offline selection: **164 passed, 2 PostgreSQL-dependent skips,
1 optional real-model deselection**, `artifacts/stage9e1/20261119T051606Z/completed-unit.xml`.
It covers new budgets, successful finalization, abstention, exact duplicate rejection,
tool failures, invalid citations, unsupported hypotheses, schema failures and the
historical prompt hash. Ruff passed. PostgreSQL/MCP security/recovery results and
final preservation checks are recorded in the verification addendum below.

A final mismatched-hypothesis test exposed over-eager deduplication: the new code
removed the assessment copy even when the top-level copy differed. The one failing
reproduction is preserved in `dedup-before.xml`. Compaction now removes **only exact
duplicates**. After that correction, the completed-source offline selection passed
**167 tests, with 2 PostgreSQL-dependent skips and 1 optional real-model deselection**,
`artifacts/stage9e1/20261119T051606Z/final-after-dedup.xml`.
The final-source replay reproduced the same measured byte counts and evidence hashes.

Initial development failures are preserved, not counted as final passes:
`initial-unit.xml` had **44 failures / 104 passes / 2 skips** during a response-handler
refactor. After correcting the local `planning` flag, `corrected-unit.xml` had
**2 failures / 146 passes / 2 skips**: one new test used a fixture without model-call
bindings, and historical prompt reproduction detected a changed shared system text.
The binding test now supplies the required synthetic call and still rejects substituted
request IDs; historical base text is preserved and new guidance is separate.
The focused correction check passed **11 tests**. These runs overlap and are not
independent model samples. Historical Stage 9E MCP timeout failures remain preserved.

### PostgreSQL/MCP security and recovery verification

The [broader regression](../evaluations/reports/stage9-operations-20261119T052411Z-0ab6fa.json)
finished with **202 passed, 26 skipped, 0 assertion failures, 1 setup error**.
Pytest execution took 531.87 s; the wrapper including setup/reporting took 546.86 s.
The error was
`test_actions_disabled_even_with_signed_grant[postgres]`: a database connection
timeout (`OperationalError`) during setup, before the control's assertions.
The [unchanged exact-case rerun](../evaluations/reports/stage9-operations-20261119T053355Z-7151c5.json)
passed **1/1**. No assertion, timeout, permission or policy was relaxed. The original
failure is retained; the infrastructure timing cause remains unresolved. This is
not a claim that the entire selected suite passed cleanly on the first attempt.

The broader run includes **24 passing durable-execution cases**, **73 passing MCP
cases** and **6 passing Stage 7 boundary cases**. They cover authenticated human
approval, changed run/arguments, revoked/expired/stale approvals, raw-resume rejection,
concurrent resume/approval protection, duplicate action effects, uncertain action
timeouts, process-crash recovery, failed verification, restricted roles and audit
immutability. SQLite durability skips are deliberate; actual PostgreSQL cases ran.
The optional real-model test was not opted in and was skipped, not counted as a pass.
Security tests use synthetic humans and isolated sandbox actions, never a production
resource or existing user incident.

The existing wrapper's separate operational aggregate reports **FAIL gates**
(`complete_operational_sample`, security, duplicate effects, recovery, verification):
this selection produced **0 of its 9 planned instrumented operation trials**.
Those aggregate rates are unmeasured (0 denominators), despite the passing pytest
control assertions. We preserve the failed gates and do not reinterpret zero counts
as measured zero failure rates or claim completion of that operational benchmark.

The final budget/security module passed **15 tests**, including the additional
independent durable gate checks for incomplete/abstained/failed states even with
leftover proposals. Evidence:
`artifacts/stage9e1/20261119T051606Z/final-budget-security.xml`.
This overlaps the earlier unit selection; counts are not added into one sample.
The broad PostgreSQL run preceded the final exact-duplicate-only compaction
correction; the completed-source 167-test unit run and offline replay followed it.

Final preservation checks found **128 protected historical/configuration files
unchanged**. AST comparisons confirm unchanged `_read`, citation/reference checks,
corroboration, root-cause/remediation validation, final-result clearing, strict-schema
generation and strict JSON parsing. The dedicated review database was stopped with
its volume retained. No unrelated container, volume, database or report was reset.
Ruff and formatting checks passed for the final source. Candidate-file hygiene
covered 306 files with zero findings. Configured-secret literal scans of the new
source, reports and private verification text also passed; these are local text
checks, not an exhaustive secret-detection or Git-history audit. Detailed evidence
is in `artifacts/stage9e1/20261119T051606Z/hygiene.json` and
`artifacts/stage9e1/20261119T051606Z/configured-secret-scan.json`.

## Proposed bounded live verification — not authorized or executed

[Machine-readable proposal](../evaluations/reports/stage9e1/20261119T053707Z-35d6b0/live-plan.json).

One calibration investigation only, Groq GPT-OSS 20B, same medium reasoning and
1,600 output tokens per request. Proposed ceilings: **11 model requests, 5 read-only
MCP calls, 4 diagnostic rounds, 600 s total, 30 s/call, 20,000 estimated input units
per prompt and 160,000 cumulative estimated units including output reservations**.
No probes, retries, actions, model promotion or benchmark expansion. Stop at the
first provider/validation/quota/timeout/budget error. Reset-aware pacing remains.

Maximum requested output is 17,600 tokens. At the checked published $0.075/M input
and $0.30/M output prices, the estimate-based worst reservation is **$0.01596**:
142,400 input units plus 17,600 output units. Proposed application ceiling: **$0.05**.
These are accounting estimates, not an invoice guarantee or an account-side cap.
No paid-plan upgrade is requested. The byte-based ceiling does not prove compliance
with an 8,000-TPM quota; an oversized request must still fail closed. The future
approved runner must enforce these exact limits and record complete sanitized
decision/timing/estimate metadata before making requests.

PASS would require actual completed, evidence-grounded diagnosis with unchanged
validation, required tool coverage and zero effects. Safe abstention/incomplete
results demonstrate safety but fail completion for the answerable calibration case.
Any provider error or invalid evidence blocks expansion. This stage does not ask
to execute that plan; fresh explicit approval would be required.

**Verdict: CONDITIONAL for the offline implementation; BLOCKED for Stage 9F.**
Real-model completion, exact HTTP 413 quota calculation and post-change diagnostic
accuracy remain unverified. No commit, push or deployment was performed.

[Final machine-readable summary](../evaluations/reports/stage9e1/20261119T053707Z-35d6b0/summary.json).
