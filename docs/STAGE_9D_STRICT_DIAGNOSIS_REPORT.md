# Stage 9D — Strict diagnosis reliability investigation

Initial investigation: 18 November 2026; offline review resumed 19 November 2026.
**Verdict: BLOCKED for reliable full diagnosis and a five-incident benchmark.**
Offline corrections are implemented. After explicit budget approval and a passing
unchanged PostgreSQL gate, five real Groq GPT-OSS requests were made. Basic JSON,
minimal diagnosis and the actual health-tool call passed. Full diagnosis again
failed at Groq; structured continuation hit a token rate limit. No full LangGraph
investigation ran. The underlying strict-generation cause is **not proven or
fixed**. GPT-OSS remains an experimental candidate; the default model is unchanged.

## 1. Root cause and evidence

The preserved [Stage 9C report](STAGE_9C_PROVIDER_COMPARISON.md) and
[request ledger](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/requests.json)
show requests 8 and 9 failed with HTTP 400 `json_validate_failed`. They reached
Groq's structured-generation enforcement boundary. Neither response reached the
local Pydantic diagnosis parser or evidence validator. Both requests had zero
tools, the same schema and prompt, and a 1,600-token completion cap.

| Suspected stage | Evidence and conclusion |
| --- | --- |
| Request construction | Offline JSON Schema meta-validation and satisfiable fixtures pass. All object properties are required, objects forbid extra properties, nullable branches and safety constants remain. This does not establish that Groq's decoder supports every schema keyword. |
| Provider generation | HTTP 400 `json_validate_failed` establishes rejection here or at provider schema enforcement. The exact internal generation failure is unavailable. |
| Strict schema enforcement | Historical provider rejection is confirmed; malformed JSON versus schema mismatch versus decoder behavior cannot be distinguished from the retained ledger. |
| Extraction/parsing | Not reached for historical D failures. A separate local validation mismatch was reproduced and corrected below. |
| Tool-result binding | Historical D contained no tools or transcript. Binding alone cannot explain those failures. Real call/result pairing is tested independently and retained in probes D/E. |
| Evidence/citations | Not reached for historical D. Offline negative tests still reject fabricated, repeated, contradicted, stale and insufficient evidence. |
| Output exhaustion | Plausible, unproven: reasoning consumes completion budget, but failed requests supplied neither completion status nor usage. Do not label the 1,600-token cap as the root cause without a controlled comparison. |
| Transport/timeout | Historical D returned HTTP 400 in 3,578 ms (Qwen) and 2,078 ms (GPT-OSS), rather than a client timeout. Stage 9C's separate metadata decompression defect was already fixed and is not a diagnosis-generation explanation. |

Historical failed generations, provider messages and private reasoning were not
retained. Consequently, reconstructing the exact failed JSON from those records
is impossible. No speculative schema simplification, token increase, reasoning
change, permissive JSON repair or provider fallback was applied.

The approved [Stage 9D live ledger](../evaluations/reports/stage9d/20261119T041059Z-ee96b9/requests.json)
reproduced the full-schema HTTP 400 in probe C. Provider request ID:
`req_01m7s01exjen2abxaz9wh1vhre`. The provider's `failed_generation` field was the
empty string; usage, completion ID and finish reason were absent. This is an empty
diagnostic field, **not proof that the model generated no tokens**, emitted malformed
JSON, or exhausted its output budget. It does not identify the offending field or
schema keyword. The exact internal cause remains unavailable.

Probe D's separate structured continuation received HTTP 429 `rate_limit_exceeded`,
provider error type `tokens`, with an 8,000-token limit and `Retry-After: 19`.
That is a token-quota failure, not evidence of another schema/grounding failure.
The coordinator stopped without retrying, as approved.

The C replay regression reconstructs the historical request from its preserved
projected evidence and obtains the original hashes:

- Messages: `569109caeee20ef05dc4201632b0a5297815fd6d3f655a02e25b39bf03a867fd`.
- Response format/schema: `a947f4e34f68b2fdc19b4232f5be37aa6f1c11b858723ccc79e149b9225c2a90`.

New live fixtures will have fresh incident/run/request identities. That replay
proves request-construction equivalence offline; it is not a new provider result.

## 2. Minimal corrections supported by offline evidence

### Local strict-contract mismatch

Before the correction, three intentionally invalid provider outputs were accepted:
omitting `human_approval_required`, omitting `automatic_action_executed`, and
supplying confidence as a numeric string. All three violate the declared wire
schema. Pydantic supplied safe defaults or coerced a type. This did **not** grant
approval or execute an action, and it cannot explain an upstream HTTP 400.

Two further reproductions confirmed that even strict Pydantic literal validation
accepted numeric `1`/`0` for the boolean approval/action flags. The parser now also
checks the original JSON boolean type. Both failing reproductions are retained in
`artifacts/stage9d/boolean-before.xml`; this closes the same wire-contract gap.

`parse_model_output` now uses strict JSON type validation and recursively requires
the explicitly supplied fields promised by the wire schema. Domain-model defaults,
stored state, schemas and approval controls are unchanged. Missing fields are
rejected, rather than synthesized. The five equivalent regression cases failed
before correction and pass after correction; both results are preserved.

### Failure visibility

Previously, the production adapter collapsed HTTP failures into `MODEL_HTTP_ERROR`
and schema/parser failures into `MODEL_OUTPUT_INVALID`. Existing safe error codes
remain, with content-free diagnostic metadata attached to failures/replies and
emitted through the existing structured JSON logger's `event` field.

Diagnostics distinguish request construction, tool binding, provider rejection,
provider schema enforcement, response extraction, JSON parsing, schema validation,
empty output, refusal, token exhaustion, transport timeout and cancellation.
They record bounded correlation IDs, HTTP status, completion status, reported
input/output/reasoning token counts, body length and elapsed timings when available.
Unknown/missing usage stays null. Validation records contain error types and
schema-owned field paths, never Pydantic inputs, context or messages.

If Groq supplies `error.failed_generation`, it is inspected only in memory for
JSON/type/required-field failures. Only lengths and sanitized validation categories
are recorded. It is never accepted as a response, even if locally schema-valid.
These diagnostics do not claim provider grammar or factual correctness.

After the live run, offline regressions tightened two diagnostic labels: an empty
provider diagnostic is now `empty_provider_diagnostic`, and HTTP 429 is explicitly
`provider_rate_limit`. The original live ledger remains unchanged: its nested
`response_parsing` label reflects validation of an empty error field, not a local
parse failure of an accepted completion. Its D `provider_request_rejected` label
is disambiguated by the preserved HTTP 429/code/type. No live retry was used to
verify this metadata-only correction.

## 3. Files changed

- `opspilot/agent/providers.py`: strict provider-output parser and diagnostic boundaries.
- `opspilot/agent/diagnostics.py`: new content-free metadata and failure classifier.
- `scripts/diagnose_stage9d.py`: new isolated A–E probes, default plan-only command,
  bounded live coordinator using the existing dedicated test controller and reader MCP.
- `tests/test_stage9d_diagnosis.py`: new schema, parser, replay, probe and diagnostic regressions.
- This report and new machine-readable verification artifacts/reports.

No dependency, default-model, authorization, remediation, checkpoint, simulator,
frontend or deployment configuration change is part of this stage. Historical
reports and evaluation data are preserved and checked against a hash manifest.

## 4. Offline verification

Environment: Windows, CPython 3.12.3; Pydantic 2.14.2, LangGraph 1.2.19,
MCP 2.3.0, httpx2 2.16.0, jsonschema 4.26.0, Pytest 9.2.0, Ruff 0.17.3.
Existing locked dependencies were used without installation or upgrades.

| Check | Actual result |
| --- | --- |
| Initial agent/9C baseline | 42 passed, 2 PostgreSQL-dependent skips, 1 real-model test deselected; `artifacts/stage9d/baseline.xml`. |
| Strict-contract reproduction before correction | 3 expected test failures, 26 deselected; `artifacts/stage9d/wire-contract-before.xml`. The adapter incorrectly accepted the invalid inputs. |
| Agent/9B/9C/9D after parser correction | 87 passed, 2 PostgreSQL-dependent skips, 1 real-model test deselected; `artifacts/stage9d/offline-after.xml`. |
| Contracts after diagnostic logging/cancellation change | 59 passed; `artifacts/stage9d/final-contracts.xml`. |
| After boolean-literal correction | 88 passed; diagnosis, 9B/9C, Groq and release-hygiene tests; `artifacts/stage9d/final-parser.xml`. |
| Broad MCP/agent/approval/recovery regression | 193 passed, 26 skipped, no failures/errors; [machine report](../evaluations/reports/stage9-operations-20261118T125707Z-9a0008.json). This run preceded the final boolean-type/extraction tightening; a final focused recheck follows below. |
| Pre-live diagnosis-only suite | 42 passed; `artifacts/stage9d/diagnosis-final.xml`. |
| Final source/unit review (19 November) | 89 passed, no skips/failures/errors; `artifacts/stage9d/final-review.xml`. Includes diagnosis probes, 9B/9C, Groq contracts and hygiene tests. |
| Post-live diagnostic regressions | 91 passed, no skips/failures/errors; `artifacts/stage9d/post-live-regression.xml`. Empty provider diagnostics and quota errors are distinguished without retries. |
| Focused PostgreSQL recheck | 98 passed, 6 skipped, 1 failure, 1 setup error; [preserved machine report](../evaluations/reports/stage9-operations-20261118T130555Z-8ee063.json). Details below; not a clean pass. |

These are deterministic fixtures, mock HTTP contracts and real local infrastructure
tests. They are **not genuine LLM reasoning or model-accuracy measurements**.
Intermediate command-selection errors ran zero tests and were corrected; they do
not count as test passes. Failed reproduction artifacts have not been deleted.

The broad run's skips were one optional real-model smoke and 25 SQLite variants
that require PostgreSQL locking/roles/checkpoint durability. The corresponding
PostgreSQL variants ran; checkpoint guarantees were not substituted with memory.
This was a selected relevant regression, not a claim that the entire repository or
all operational benchmark gates passed. Reports are additive, not independent
sample counts to sum into a model benchmark.

The focused recheck had two infrastructure-sensitive results:

- `test_agent_refuses_operator_credential[postgres]`: database connection timeout
  during test setup, before the authentication assertion ran.
- `test_unapproved_actions_fail_closed[postgres-expired]`: observed `TIMEOUT`
  instead of the expected `APPROVAL_EXPIRED`. The test failed at that assertion;
  its final action-count assertion was not reached. This result alone does not
  prove either an authorization bypass or zero action effects.

Their exact rerun results are recorded below. Neither assertion, connection
timeout, authorization policy nor test expectation was relaxed. The original
failed run remains preserved; a successful rerun would not erase its result or
prove its underlying timing cause resolved.

On 19 November, the unchanged exact rerun returned **1 passed, 1 setup error**:
[rerun report](../evaluations/reports/stage9-operations-20261119T040405Z-458000.json).
The expired-approval case passed, including the assertion of zero action records.
The operator-credential case again hit the database connection timeout during
migration setup. That case passed in the earlier broad run, but its final recheck
remains unresolved. An initial rerun attempt also hit the unchanged 15-second
Docker identity-inspection timeout and ran zero tests. Docker startup first
returned an engine `_ping` HTTP 500, then succeeded. No infrastructure timing cause
is established from these observations. No timeout or test expectation was widened.

The final unchanged PostgreSQL gate then **passed (1 test)**:
[gate report](../evaluations/reports/stage9-operations-20261119T040953Z-ed6a83.json).
Live execution began only after this result and the explicit conditional approval.
The intermittent earlier setup failures remain an environment reliability limit.

Schema testing covers full and minimal satisfiable contracts, required fields,
types, extra fields, approval/action literals, bound citation enums, malformed,
truncated, empty and incomplete responses. Draft 2020-12 validation is an offline
schema check, not certification of the hosted provider's supported subset.

Grounding testing is separate: schema-valid but contradicted/low-confidence
diagnoses and invented citations are rejected. Existing workflow tests exercise
stale/empty evidence and insufficient evidence. Citation membership and independent
corroboration remain necessary gates; they cannot prove causal or numerical
correctness of every sentence. Model root-cause accuracy remains unmeasured.

## 5. Reproducible isolation probes and approved live budget

Print the plan without loading credentials, starting fixtures or making requests:

```powershell
Set-Location D:\Projects\OpsPilot-AI
.\.venv\Scripts\python.exe -m scripts.diagnose_stage9d
```

| Probe | Request and assessment | Maximum inference calls |
| --- | --- | ---: |
| A | Strict basic JSON, no tools; schema validity only. | 1 |
| B | Minimal diagnosis with existing `RootCause` type or null, no tools; isolation only, never a production recommendation. | 1 |
| C | Full unchanged `StrictDiagnosis`, no tools; reproduces 9C D construction and independently validates evidence. | 1 |
| D | Actual generated health-tool call, real MCP result with matching call ID, then strict full diagnosis. Fresh evidence gets a distinct registry ID. No tools declared on the structured request. | 2 |
| E | Existing LangGraph investigation with model-selected read tools, conditional routing, and all existing evidence/remediation gates. Only attempted if A–D pass. | 14 |
| Total | One calibration case (`op5-001`), never held-out answers in agent context. No automatic retries, extra model-list calls or remediation. | **19** |

Approved model: Groq `openai/gpt-oss-20b`, medium reasoning, temperature 0.2,
`include_reasoning=false`, streaming off, original **1,600 output-token cap per
request**, maximum **30,400 output tokens across 19 requests**. Request input is
bounded to 65,000 serialized UTF-8 bytes including a 512-byte accounting reserve;
this is a conservative token estimate, not a measured tokenizer count.

Prices checked in the [official model documentation](https://console.groq.com/docs/model/openai/gpt-oss-20b):
$0.075/million input tokens and $0.30/million output tokens. Reserving 65,000
input-token equivalents and 1,600 output tokens for each of 19 calls gives
**$0.101745** at those list prices. Approved application reservation/spending cap:
**$0.15 USD**. Missing usage retains the complete reservation; failed requests count
toward the call ceiling. This is not an invoice or a provider-side billing cap.
Keep paid billing disabled or set a provider account limit if a hard account cap is
needed. No Free Plan/account billing status is asserted from the key.

Twelve-second request pacing, 15-second HTTP timeout, 180-second total E workflow
budget, maximum eight diagnostic tools. Stop on authorization/quota rejection or
budget exhaustion. If C fails, E remains gated; D can still isolate continuation.
No automatic budget increase, retry, alternate model or larger-output experiment.
Any follow-up intervention needs a new evidence-backed plan and approval.

The user explicitly approved this bounded plan on 19 November, conditional on the
unchanged database gate passing. That condition passed. The plan was executed once
and stopped after five requests; 14 calls were unused. The following is the
reproduction command, **not authorization to start another live run or retry the
quota failure**. A follow-up experiment needs a new approved plan.

```powershell
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --pull never --wait review-db
.\.venv\Scripts\python.exe -m scripts.diagnose_stage9d --execute-approved-plan
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

The execution flag acknowledges the separately approved provider budget; it is
not an authorization token and cannot approve a remediation. The existing backend
human-approval service remains the sole authority for sandbox actions. The live
runner has only reader MCP credentials, actions disabled, fresh UUID test schemas,
fixture-table hashes and an action-record count. It retains new timestamped reports
without overwriting historical experiments. It does not start the five-incident
benchmark.

The [Groq structured-output documentation](https://console.groq.com/docs/structured-outputs)
documents required fields, `additionalProperties=false`, model-specific support
and separation from tool use. The [reasoning documentation](https://console.groq.com/docs/reasoning)
describes model-specific reasoning controls. Documented support does not override
the recorded 400 responses or establish correctness of a diagnosis.

## 6. Live results, latency and cost

Actual model: **Groq `openai/gpt-oss-20b`**, with the approved settings above.
[Live report](../evaluations/reports/stage9d/20261119T041059Z-ee96b9/report.json).

| Request | Actual outcome | API latency | Reported input/output tokens |
| --- | --- | ---: | ---: |
| A — basic strict JSON | PASS, locally schema-valid; not a diagnosis | 328 ms | 177 / 50 |
| B — minimal diagnosis | PASS, locally schema-valid; not a production recommendation or factual-accuracy pass | 891 ms | 2,711 / 464 |
| C — full diagnosis, no tools | FAIL, provider HTTP 400 `json_validate_failed`; local schema/grounding validation not reached | 2,656 ms | Unavailable |
| D — tool selection | PASS, provider function call validated and actual read-only MCP health tool executed | 515 ms | 563 / 41 |
| D — structured continuation | BLOCKED, HTTP 429 token rate limit; no completed output to validate | 187 ms | Unavailable |
| E — full LangGraph investigation | NOT RUN, A–D qualification gate failed | Unavailable | Unavailable |

API latencies exclude deliberate pacing, database setup, MCP execution and shutdown.
Their measured sum is 4.577 seconds; it is not end-to-end investigation latency.
The report's per-probe wall times include pacing. Five mixed success/error calls
are not a useful model-latency benchmark or a p50/p95 investigation sample.

**5/19 approved requests used**, no retries. Reported usage from three successful
responses: **3,451 input / 555 output tokens**, including 305 reported reasoning
tokens already counted within output. Usage for two rejected requests is unknown.
Successful-response list-price estimate: **$0.000425325**, a partial estimate only.
Conservative accounting with full reservations retained for unknown usage:
**$0.0044604**, below the $0.15 application ceiling. Actual total invoiced cost and
account tier are unverified; failed requests are not asserted to be free.

The controller retrieved five real, projected MCP observations: `get_incident`,
`get_service_metrics`, `search_service_logs`, `get_dependency_status`, and
`list_recent_deployments`. A sixth read, `get_service_health`, followed the actual
model call `fc_d5c7324a-9bd7-4805-a015-9ba07be79d74`. It was the single offered,
forced health function, not an autonomous choice among the seven diagnostics.
MCP returned a real result bound to that call; the full investigation/tool-choice
test E remained gated.

The retained live evidence SHA-256 is
`48f3ec49a4b48d8f3f2f4d8b460fc1373ec46981b976a53cc2905712f68486b2`.
The live runner
retained the packet hash and inventory rather than the projected packet itself;
current numeric telemetry and B's text cannot be independently re-inspected from
that artifact. No factual diagnosis is claimed from those missing payloads.
This is a reproducibility limitation; the deterministic recipe and preserved 9C
packet support offline schema replay but do not reconstruct the fresh live IDs.

Accepted full diagnoses: **0**. Full diagnoses reaching evidence grounding: **0**.
Root-cause accuracy: **unmeasured (0/0 scored investigations)**. Probe A/B success
does not establish causality or citation correctness. There is no demonstrated
before/after real-model reliability improvement.

The fixture-table hash was unchanged and the actual action-record count was **0**.
No state-changing tool, grant or approval was supplied. Private provider messages,
raw failed generations, reasoning and credentials were not retained or printed.

## 7. Safety, remaining failures and benchmark gate

The investigation graph still has seven read-only MCP tools and cannot approve
itself. Human approval, exact action binding, service/run scoping, replay defenses,
durable action records, reconciliation and transactional idempotency are unchanged.
Invalid model responses cannot create accepted recommendations or initiate actions.
No timeout retry was introduced; no diagnosis is repaired or substituted.

The unresolved blocker is the exact hosted strict-generation failure. Possibilities
include provider decoder/schema interaction, generation behavior and completion
budget; the historical evidence does not rank these conclusively. The new local
parser correction strengthens rejection and **must not be described as fixing the
provider failure**. Small calibration probes cannot establish population accuracy
or default-model readiness even if successful.

**A five-incident benchmark cannot safely begin yet.** It remains gated on separately
approved A–E execution, an accepted evidence-grounded investigation, resolution or
clear diagnosis of remaining failures, and a separate benchmark budget. No default
promotion, deployment, commit or push was performed.

## 8. Final verification evidence

[Final machine-readable summary](../evaluations/reports/stage9d/20261119-final-1971e1/summary.json).
The earlier `20261119-offline-a0d051` summary describes the phase before live-budget
approval; its zero-inference counts have been preserved as historical phase data.

- Offline source/contract verification: **PASS**, post-live unit selection 91 passed;
  pre-live diagnosis-specific selection 42 passed. Ruff checks the repository; all
  four changed/new Python files pass formatting checks.
- Infrastructure/security regression: **CONDITIONAL**, broad run 193 passed,
  26 skipped; focused run 98 passed, 6 skipped, 1 failure, 1 setup error; exact
  rerun 1 passed, 1 setup error. Do not replace these with a combined clean total.
- Parser before/after: five invalid response vectors reproduced as failing tests
  before correction, rejected after correction under equivalent fixture conditions.
  This demonstrates stronger local contract enforcement, not improved model accuracy.
- Historical preservation: 74 protected historical reports/data/configuration files
  checked, no changes. `artifacts/stage9d/20261118T124814Z/protected-hashes.json`
  contains the manifest. Locked dependencies and protected agent schemas/workflow
  files are unchanged.
- Secret scan before final report assembly: 268 candidate files, zero findings;
  later pre-live scan: 271 candidate files, zero findings. Bounded configured-secret
  checks of 35 new evidence files found zero hits. Final release-scan results are
  **276 candidate files, zero findings**, recorded in the final summary.
  Test credentials and private logs remain excluded
  from release paths; a scan is not a proof that arbitrary future outputs are safe.
- Five approved live requests, no accepted full diagnosis, no default promotion, no deployment,
  commit or push. The dedicated review database is stopped after verification,
  with its named volume retained; other project containers/volumes are untouched.

The full Stage 9D objective remains **BLOCKED** by the unresolved hosted full-schema
failure and quota-blocked continuation. The conditional budget was approved, the
unchanged database gate passed, and the approved experiment stopped as specified.
Offline corrections strengthen validation and diagnostics; neither the exact
provider cause nor a successful real-model correction has been demonstrated.
No further provider requests or five-incident benchmark are authorized by this run.
