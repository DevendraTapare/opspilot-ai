# Stage 9E.2 — Live verification preflight

Date: 19 November 2026. **CONDITIONAL; explicit approval required.**
Actual provider requests: **0**. Actual inference spend: **$0**. No remediation,
commit, push or deployment. Stage 9F remains gated.

## Review of the previous proposal

The [Stage 9E.1 plan](../evaluations/reports/stage9e1/20261119T053707Z-35d6b0/live-plan.json)
was explicitly a proposal, not an executable $0.05 guarantee. The old
`scripts.verify_stage9e` runner still permits 14 requests and $0.15, and its budget
can release reservations after low reported usage. **Do not use that runner for
Stage 9E.2.** Historical scripts/reports are preserved.

This preflight adds a dedicated, default-plan-only runner and an experiment-local
reservation guard. It proposes a **lower $0.02 application ceiling**, within the
original $0.05 outer budget, because an actual provider invoice cap cannot be
certified. The [new plan, version 9e2-1](../evaluations/reports/stage9e2/20261119-preflight/plan.json)
requires fresh approval, including acceptance of that billing limitation.

## Exact request and token plan

One controlled checkout investigation, calibration case `op5-001`, using experimental
Groq **`openai/gpt-oss-20b`**. The case identifier and private grade stay in the trusted
controller; the agent receives ordinary incident identity/goal and MCP evidence.
No preliminary inference probes, model-list API calls, benchmark expansion or
fallback model. No default-model configuration changes.

| Limit | Enforced value |
| --- | ---: |
| Investigations | 1 attempt |
| Provider requests | At most 11 |
| Read-only MCP diagnostic calls | At most 5, including the initial incident read |
| Diagnostic rounds | At most 4 |
| Input estimate per request | 20,000 UTF8 byte-equivalent units including 512 framing reserve |
| Output per request | 1,600 tokens, including reasoning |
| Cumulative output maximum | 17,600 tokens |
| Cumulative estimated input + output reservation | 160,000 units |
| Investigation duration | 600 s, including pacing |
| Per model/tool operation | At most 30 s, or remaining total duration |
| Minimum request spacing | 12 s; token-reset duration plus 1 s when greater |
| Local cumulative reservation ceiling | **$0.02** |
| Automatic retries / inference probes | 0 / 0 |

The eleven slots are: **one triage**, up to **four planning/assessment pairs**,
**one root-cause proposal**, and **one remediation proposal**. The last proposal is
text only. Final recommendation construction does not add an LLM request. The model
chooses diagnostics from the existing read allowlist; this is not a prescribed
tool sequence. The five MCP calls are the initial incident read plus up to four
selected diagnostics. SDK initialization/discovery is not an inference request or
a diagnostic `call_tool` operation.

Medium reasoning, temperature 0.2, `include_reasoning=false`, `stream=false`, one
completion per request. Tool use and strict output remain separate requests. The
transport rejects undeclared top-level parameters such as `n`, another model,
larger output limits, or an incompatible request format. Actual provider input
tokens are unknown before execution; estimates are not presented as exact usage.
Fixture setup/cleanup is separate from the 600-second investigation deadline.

## Spending guard: guarantee and limitation

At the checked [Groq list prices](https://console.groq.com/docs/model/openai/gpt-oss-20b),
input is $0.075/M tokens and output $0.30/M. With eleven requests, the worst
estimate-based reservation is:

`(160,000 - 17,600) × $0.075/M + 17,600 × $0.30/M = $0.01596`.

The guard uses **integer nanodollars**, 75 per input unit and 300 per output token.
For each request it:

1. Validates the exact model, endpoint, request parameters and token limits.
2. Under a lock, checks `accounted + full_next_reservation <= $0.02`, as well as
   request count, token budgets and deadline, **before transport dispatch**.
3. Adds the complete reservation and writes the ledger before sending anything.
   Failure to persist blocks dispatch. Only one request may be in flight.
4. **Never refunds a reservation**, even after lower reported usage. Missing,
   partial or uncertain usage, cancellations and failures retain the full amount.
5. If reported usage exceeds its reservation/limits, records the overage and stops
   all later calls. It cannot undo a charge already reported by a provider.

The ledger is experiment-local, not shared with unrelated applications. Reopening
the same ledger as a fresh budget is rejected. There is no resume, restart or second
attempt under this approval; creating another run requires new authorization.
The execution flag is a trusted operator acknowledgment, not model or MCP approval.
The agent cannot invoke the experiment runner.

**Hard local admission guarantee:** no request is dispatched when its complete
estimate-based reservation would cross $0.02. Tests check the downstream call count
and persisted reservation. This is stronger than waiting until after a response
to notice that a local estimate crossed the ceiling.

**Not guaranteed: actual Groq invoice <= $0.05.** The estimator is a conservative
byte-based accounting policy, not a certified provider tokenizer/billing oracle.
Account tier and invoice treatment are unverified. Other applications are outside
this ledger. Groq's [spend-limit documentation](https://console.groq.com/docs/spend-limits)
also describes delayed spend tracking and possible overshoot, so an account setting
would not establish an exact per-investigation cent-level guarantee here.
Synthetic overage tests explicitly demonstrate that already-reported charges cannot
be prevented retroactively; they are not actual billable results.

The safer proposal is the **$0.02 local cap**, leaving $0.03 below the requested
outer budget. It reduces exposure but does not convert an estimate into an invoice
guarantee. If a strict actual-bill $0.05 limit is mandatory, the live test remains
**BLOCKED**; keep this stage offline rather than represent the cap as proven.
No billing upgrade, account setting or cloud resource was changed.

## Stop conditions and safeguards

Stop the single attempt on **HTTP 400, 413 or 429**, and also every other non-200
response, transport/timeout error, access rejection, invalid/incomplete structured
output, unsupported/invalid citations, budget exhaustion, deadline or ledger failure.
No automatic retry, alternate key, fallback model, second incident or extra probe.
`Retry-After` is not permission to retry. Any uncertain request retains its reservation.

Only the unchanged reader identity and read-only MCP allowlist are used. The trusted
test environment creates its separate UUID schema and authorizer with
`actions_enabled=false`. The agent receives neither action tools nor human approval
capability. No approvals, grants or action executions are created by this runner.
The post-run checks require unchanged simulator fixture hashes and zero action
execution records. Human approval and transactional idempotency code are untouched.

Schema closure, required fields, citation syntax and observed-ID restrictions,
tool/result provenance, freshness, corroboration, hypothesis/confidence gates and
failure clearing remain unchanged. All **204 protected existing files** were
byte-identical at preflight verification, including previous agent, gateway,
durability, configuration, dependency and historical report files.

## Exact success criteria

Both branches require all budget/scope/side-effect checks, retained authoritative
evidence, appropriate diagnostic selection, valid structured decisions, and an
independent review against actual evidence. The model cannot judge its own success.
No additional paid evaluator requests are authorized. The runner initially records
**REQUIRES_INDEPENDENT_REVIEW**, never automatic semantic PASS.

**A. Supported final diagnosis:** the graph completes, all existing evidence gates
pass, root cause and proposal match the observed service/evidence, explanations
preserve measured values and units, alternatives are assessed, and the private
controller grade confirms correct diagnosis and required-tool coverage. The reviewer
must check semantic support rather than infer it merely from schema validity or
the grader's coarse action-to-mechanism mapping. The proposal requires separate
human approval and is not executed.

**B. Correct evidence-based abstention:** the model explicitly returns a validated
`assessment.decision=abstain` and final `run_status=abstained`, with no failed decision,
no root cause/proposal/action and a precise explanation of missing or contradictory
evidence. The review must confirm that those gaps actually exist after reasonable,
appropriate checks and that the agent did not overlook already supplied evidence
or skip available decisive diagnostics. The supporting observation IDs must be valid.
A transport error, validation rejection or exhausted budget does not qualify.

The selected calibration case is normally answerable. A safe abstention on its
sufficient telemetry is **not** a successful diagnosis or task completion. An
unexpected genuinely insufficient packet may support branch B only after explicit
independent review. Preserve the unchanged private grader result separately; do not
rewrite a failed diagnosis grade into an accuracy success. Report a correct
abstention as abstention, with zero accepted diagnoses.

An **incomplete** result, including `budget_exhausted`, is never successful diagnosis
or correct model abstention. Partial root causes/proposals are cleared. A failed
or inconclusive pilot does not authorize further calls or Stage 9F expansion.

## Expected outputs

One fresh report directory under `evaluations/reports/stage9e2/` containing:

- Versioned plan and pre-dispatch cost/request ledger, including unknown usage.
- Validated per-node decisions, evidence IDs, sanitized provider request IDs,
  response status, tokens when supplied, and latency.
- Final structured state with the complete projected evidence and tool history.
- Private-controller grade, fixture-hash comparison, action-record count and
  review-required classification; no fake success.
- A separate independent evidence-review note before reporting any final PASS.

No raw prompts, provider error messages, private reasoning or credentials are
persisted in the transport ledger. Model-generated recommendation/assessment text
is validated and retained for evidence review, not treated as trusted instructions.

## Offline verification

- Initial guard suite: **22 passed**; planned mock workflow suite: **23 passed**.
- Extended suite first recorded **25 passed, 1 failed** because a new direct-adapter
  test omitted its required `observations` context. The test now supplies that valid
  empty context; no runtime evidence check was weakened.
- First broader regression: **194 passed, 3 skipped, 1 failed, 1 real-model
  deselected**. The unchanged existing slow-drip deadline test failed its 0.3 s outer
  bound. Its exact unchanged rerun passed **1/1**; timing cause remains unresolved.
- **Final complete offline selection: 198 passed, 3 PostgreSQL-dependent skips,
  1 optional real-model deselection**. Includes the final 26 preflight cases,
  budgets, response/schema/citation failures, unsafe hypotheses, incomplete-result
  rejection, tool provenance and adversarial boundary checks.
- The full eleven-request/five-tool mock workflow completed within the exact new
  reservation limits with missing usage on every response, retaining all reservations.
  This is a fixture test, not genuine inference or an accuracy measurement.
- Ruff and formatting are checked for the new files. No database integration or
  provider smoke was run in this preflight; PostgreSQL-dependent skips are explicit.
  Stage 9E.1's real-MCP/PostgreSQL outcomes and limitations remain historical evidence.
- Final Ruff/format checks passed. Local candidate-file hygiene scanned **312 files
  with zero findings**. Configured-secret scans of new text artifacts are recorded
  alongside the JUnit evidence; these are not a Git-history or exhaustive secret audit.

Raw evidence is retained under `artifacts/stage9e2/20261119T061523Z/`, including the
initial failures, exact rerun and final JUnit report. Selections overlap and must not
be added into one benchmark sample.

## Files and approval boundary

New files only: `scripts/stage9e2_budget.py`, `scripts/verify_stage9e2.py`,
`tests/test_stage9e2_preflight.py`, this report, and additive preflight evidence/plan.
Existing architecture, schemas, default configuration and historical results are
preserved.

Safe plan-only command, with no key loading or provider request:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_stage9e2
```

The execution flag must **not** be run before fresh explicit approval of version
9e2-1, including the $0.02 reservation ceiling and invoice limitation. Prior
Stage 9E approval was consumed and does not authorize this attempt.

**Preflight verdict: CONDITIONAL.** Offline controls pass. Live execution is paused
at the user's explicit approval boundary. The HTTP 400/413 causes, possible quota
rejection, real-model completion and actual billing remain unverified. A strict
$0.05 invoice guarantee is not established; if required, the live run is blocked.

[Machine-readable preflight summary](../evaluations/reports/stage9e2/20261119-preflight/summary.json).
