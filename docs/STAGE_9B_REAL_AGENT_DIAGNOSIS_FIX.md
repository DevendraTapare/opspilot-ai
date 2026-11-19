# Stage 9B — response binding repairs and genuine-model rechecks

8 November 2026 · `D:\Projects\OpsPilot-AI`

**CONDITIONAL — structural repairs passed regression checks, but the real-model
diagnosis objective remains unmet: 0/3 repaired investigations completed.** The
five-case evaluation was not run. No larger benchmark, model switch, fallback,
automatic retry or autonomous remediation occurred.

The [Stage 9A report](STAGE_9A_GROQ_VALIDATION.md), [Stage 9 report](STAGE_9_REAL_LLM_VALIDATION.md),
historical artifacts and ground-truth labels are preserved. New
[machine-readable before/after results](../evaluations/reports/stage9b-real-investigation-20261108.json)
link every attempt, request status, source fingerprint and metric denominator.

## 1. Original three failures

The three historical attempts were fresh incidents from **the same calibration
recipe `op5-001`**, not three distinct benchmark scenarios. The controller can
identify that recipe; the model receives only the public incident request and
positively projected operational observations. It does not receive private fault
labels, seeds or expected answers.

| Stage 9A investigation identifier | Model response and parsed output | Actual MCP tools and evidence | Immediate rejection | Factual correctness / formatting-only assessment | Limits involved |
|---|---|---|---|---|---|
| `b6f9a643-031b-4f7c-8100-6db9acc28f3b` | Valid typed triage and planning; assessment HTTP 400 `json_validate_failed`; retained safe metadata says failed generation was not JSON. No parsed assessment/root cause exists. | Bootstrap `get_incident` → `e001`; model-selected `get_service_metrics` → `e002`. Current window: 30 requests, 27 errors, worker utilization 1.0, DB utilization 0.0, p95 100 ms; prior baseline: 12 requests, zero errors, worker utilization 0.1875. | Provider rejected assessment before the application's Pydantic/citation validator could run. | No diagnosis to fact-check. Invalid provider JSON is confirmed; the exact malformed syntax and any underlying reasoning error are **not recoverable** from retained safe metadata. Formatting-only quality cannot be established. | 2/8 tools, 3/14 model calls, 5,016 ms vs 180 s. No graph budget exhaustion. Provider rejected output without a finish reason/token-usage record; output truncation is not established. |
| `ac8644b7-18a2-4b9d-a701-352e63cb041c` | Assessment JSON parsed under the then-current schema. Decision `investigate`, confidence 0.2. Citation arrays held full explanatory strings starting with `e002`, plus an unavailable-evidence statement. | Bootstrap `get_incident` → `e001`; model-selected `get_service_health` → `e002`. Same measured current-window values as above. | `_refs` requires exact existing IDs, so prose and missing-data statements were rejected; they were never silently rebound to `e002`. | The immediate rejection was citation formatting/binding. Quality was **not merely formatting**: 27/30 was misstated as 93%, and zero DB usage was presented as potentially supporting DB allocation failure without corroboration. No final diagnosis was emitted. | 2/8 tools, 3/14 model calls, 4,454 ms. No time/tool/model budget exhaustion. HTTP responses were 200; no reported output truncation. |
| `64108f8c-acf0-423b-aa70-4e259e104873` | Triage parsed; planning HTTP 400 `tool_use_failed`. No parsed diagnostic function call exists. | Only bootstrap `get_incident` → `e001`; no model-selected diagnostic ran. | Provider rejected its generated tool call before MCP execution. | No diagnosis to judge. Exact tool syntax/argument failure is unavailable because raw failed generation was intentionally not retained. Do not infer an authorization or citation failure. | 1/8 tools, 2/14 model calls, 2,063 ms. No graph budget exhaustion; provider-side truncation is unproven. |

Original artifacts remain in `artifacts/stage9a/groq-20261108T054000Z-1ecf1f/`,
`groq-20261108T054153Z-c7b465/` and `groq-20261108T054320Z-a4d0ef/`.
Those records establish the rejection boundary, not the preview provider's internal
decoder failure. Claiming a precise internal cause beyond that evidence would be
speculation. The missing raw generations are a deliberate privacy/secret boundary.

## 2. Groq compatibility verified against current official documentation

| Contract | Documented support and configuration used |
|---|---|
| Model | Exact unchanged **`qwen/qwen3.8-27b`**, preview; no silent model replacement |
| Tool calling | Local function/tool calling; preserve assistant call ID and matching `role=tool` result |
| `reasoning_effort` | `none`, `default`, `low`, `medium`, `high`; selected **`none`** |
| `reasoning_format` | `parsed`, `raw`, `hidden`; selected **`hidden`**. `raw` is incompatible with JSON/tool mode. `include_reasoning` is not combined with it. |
| Structured output | Model listed for JSON Schema `strict: true`; all object keys required, additional properties forbidden |
| Tools plus structured output | Not supported in one request. Planning declares tools only; assessment/finalization declares JSON Schema only. Assessment may carry a historical completed assistant/tool pair, but declares no callable tools. |
| Context / output limit | Advertised 131,072 context / 16,384 output tokens. Application limit remains **1,600 output tokens**, unchanged. |
| Other selected parameters | `temperature=0.2`, non-streaming; HTTPS, no ambient proxy, no redirects, no HTTP transport retries |
| Pacing | Minimum 12 seconds between request starts in the explicit Groq profile; charged to the unchanged 180-second total investigation budget |

Sources checked: [model specifications](https://console.groq.com/docs/model/qwen/qwen3.8-27b),
[reasoning parameters](https://console.groq.com/docs/reasoning),
[local tool-call lifecycle](https://console.groq.com/docs/tool-use/local-tool-calling),
[structured-output compatibility](https://console.groq.com/docs/structured-outputs).
These are support claims, not a factual-accuracy or availability guarantee. Actual
HTTP 400 errors persisted even with documented settings. Neither `tools` nor a
function `strict` hint is silently added to structured requests. Groq planning uses
documented function parameters plus independent application validation; the generic
OpenAI-compatible adapter retains its existing strict function hint.

## 3. Confirmed orchestration and citation findings

The previous adapter parsed `select_diagnostic_tool` arguments and discarded its
provider call ID. Each next model request was a new system/user snapshot rather
than an assistant-function/tool-result exchange. Tool data was present in the
snapshot, so **missing evidence was not the cause** of the historical citation
failure. Losing IDs was nevertheless a real protocol-attribution gap.

Evidence IDs were already stable `e001`, `e002`, etc., stored in typed graph state.
No observed LangGraph node lost or renumbered an ID. The historical rejection was
prose in citation fields, not an `e002` → different-ID serialization bug. The
existing positive projection excluded fixture causes from service logs, deployments,
health and incident metadata; it remains in place.

The strict string-pattern contract added in Stage 9A did not constrain citations
to this particular run's inventory at generation time. New requests additionally
enumerate actual available IDs in the wire schema; the independent membership,
freshness, confidence and corroboration checks still run afterward. A valid schema
or valid ID is never treated as proof of semantic causality.

## 4. Exact implementation changes

- `opspilot/agent/schemas.py`: bounded `ModelToolCall` containing provider ID,
  function name and validated diagnostic arguments; optional call/request metadata
  in tool history and pending selection. Defaults preserve older serialized records.
  Citation strings explicitly describe bare observed IDs.
- `opspilot/agent/conversation.py` (new): rebuild bounded assistant/tool pairs from
  validated state; verify ID uniqueness, exact arguments, target scope, observation
  ID, tool name, service and MCP request ID. Errors remain errors without evidence
  IDs. Enumerate available citation IDs in the output schema.
- `opspilot/agent/workflow.py`: preserve model function metadata through execution;
  bind MCP request IDs; check registry uniqueness/order against successful tool
  records before model decisions. Proactive pacing consumes total time budget
  separately from the per-request timeout. No action or approval node was added.
- `opspilot/agent/providers.py`: explicit **`groq`** profile restricted to the reviewed
  endpoint/model; documented non-thinking/hidden parameters; typed function IDs;
  paired result messages during investigation and separate tool-free root/remediation
  requests. Explicit safe refusal, empty-response and 429 error states. Schema,
  response-size, context-size and token/time/tool limits remain enforced. No JSON
  salvage, invented-reference substitution, fallback or automatic retry exists.
- `opspilot/observability.py`: permit the fixed provider name `groq` in the existing
  sanitized attribute allowlist. No diagnostic content or new trace exporter added.
- `tests/test_agent.py`: mocked compatible-provider calls now include a provider ID.
- `tests/test_stage9b_pipeline.py` (new): lifecycle, state serialization, binding,
  citation, refusal/empty/malformed/truncated output, rate-limit and pacing tests.
- `scripts/verify_stage9b.py` (new): bounded real-mode initial/five phases, fresh
  PostgreSQL schemas, real authenticated MCP, frozen rubric, safe request metadata,
  partial usage and price estimates. Five phase requires all three initial
  investigations to pass. Post-action execution/verification is not attempted.
- New dated aggregate/report and a README status pointer; previous reports, dataset
  labels, dependency locks, checkpoints and transactional action implementation
  were not rewritten or upgraded.

The graph remains evidence-driven: model-selected read, assessment conditional
route, additional investigation when requested, separate root-cause request,
separate remediation request, deterministic final record assembly. No incident-ID
rule, fixture answer, fixed diagnostic sequence or new agent framework was added.
No real root-cause/remediation request was reached in the three repaired attempts;
tool-free finalization was exercised by mocked-response regression tests only.

## 5. Reproduction before changes

Three fresh reproductions of the original recipe were attempted **once each**
before applying the core repairs. Requests remained within 8 tools, 14 model
calls, 180 seconds total and 15 seconds per call.

| Reproduction | Actual outcome | Tools | Graph latency | Usage |
|---|---|---:|---:|---|
| 1 | After health and metrics, provider returned 429; stopped without retry | 3 | 17,234 ms | Partial: 7,583 input / 1,087 output |
| 2 | Transport failure before a response status was available | 1 | 11,813 ms | Unavailable |
| 3 | Model-call timeout before a response status was available | 1 | 15,109 ms | Unavailable |

Reproduction 1 used the existing unpaced configuration. After observing its quota
failure, reproductions 2/3 were paced 12 seconds apart in the verification wrapper,
with the same application budgets and original core code. They were different
predesignated attempts, **not retries of reproduction 1**. Pacing for these two was
inside the old per-call deadline; the repaired workflow charges capacity waiting
to the total deadline instead. The network failures do not prove provider format
or citation defects were fixed, nor that this computer caused them.

Artifacts: [first reproduction](../artifacts/stage9b/before-20261108T060033Z-710c98/report.json),
[remaining two](../artifacts/stage9b/before-remaining-20261108T060430Z-56c118/report.json).
These fresh stochastic/provider-dependent outputs did not reproduce the exact
historical error sequence; the original failure analysis above uses preserved
Stage 9A evidence rather than pretending the new failures are identical.

## 6. Three repaired genuine-model attempts

One predeclared run of three fresh incidents from the same unchanged calibration
recipe, maximum **42 HTTP requests**, no retries. Actual use: **8 requests**.

| Attempt / run ID | Valid decisions | Actual tools | Final outcome | Graph latency |
|---|---:|---|---|---:|
| 1 · `04554afe-e52c-4ba4-b615-1dd13bfd114d` | 2/3 | Bootstrap incident; model-selected checkout health | Assessment HTTP 400 `json_validate_failed`; no accepted diagnosis | 26,875 ms |
| 2 · `69bb1a59-e625-4d73-b5cb-54bf20acc217` | 3/4 | Bootstrap incident; model-selected checkout health | Valid assessment/citations; next planning HTTP 400 `tool_use_failed`; no accepted diagnosis | 45,109 ms |
| 3 · `37615f6e-7d1c-4868-a9e6-7def4e103a40` | 0/1 | Bootstrap incident only | Triage HTTP 400 `json_validate_failed`; no accepted diagnosis | 10,032 ms |

Complete evidence: [repaired initial report](../artifacts/stage9b/initial-20261108T061218Z-9835b1/report.json).
Each directory contains the pre-execution plan and full projected graph snapshots.
Raw HTTP bodies, keys and private reasoning are not retained.

### Actual tool-result binding

Both selected diagnostics were `get_service_health` with exact arguments
`{"service_name":"checkout-service"}`. The successful typed model planning
outputs also retain their independently validated `DiagnosticStep` fields.

| Attempt | Model function ID | MCP request ID | Registered observation |
|---|---|---|---|
| 1 | `rc4jhzxy9` | `76111713-8a4b-40d3-80cc-d8cf79bb90b3` | `e002` |
| 2 | `wwhdn63t1` | `37e0f49b-1806-48a0-a4bd-9e4d335c87e2` | `e002` in this separate run |

The subsequent assessment request had ordered roles
`system → user → assistant(function ID) → tool(same ID) → user(contract)`.
It declared JSON Schema and **no tools**. Actual server-generated results carried
30 requests / 27 errors / error rate 0.9 / p95 100 ms / worker utilization 1.0 /
DB utilization 0.0. These came from actual simulator workloads, not static responses.

Attempt 2 returned a validated assessment using bare citations `e002`, `e002`,
`e001` across three hypothesis-support arrays. It recognized worker saturation
as a candidate, compared dependency/configuration alternatives, and requested
more investigation with confidence 0.4. Missing dependency/deployment/log evidence
was expressed as uncertainty. This was **not** an accepted root cause. In particular,
an incident timestamp cited for a deployment hypothesis cannot substantiate an
actual deployment; syntactically valid citations do not establish that claim.
The next tool-call generation failed, so independent corroboration and finalization
were never reached. No proposed restart is inferred from that partial hypothesis.

## 7. Before/after metrics and denominators

| Metric | Before repair reproductions | After repair |
|---|---|---|
| Supported completed diagnoses | 0/3 | **0/3** |
| Correct root causes / answerable attempts | 0/3 | **0/3** |
| Task completion | 0/3 | **0/3** |
| Typed valid model decisions / attempted decisions | 4/7, incomplete transport responses | **5/8** |
| Strict JSON decisions, excluding tool selections | Not a matched comparison | **3/5** |
| Typed tool selections | Not a matched comparison | **2/3** |
| Delivered assessments with valid citations | No final-diagnosis claim | **1/1** delivered schema-valid assessment; three exact-ID citation occurrences accepted |
| Unsupported final diagnoses | 0 emitted; rate unavailable | **0/0**, rate unavailable; not a 0% population result |
| Appropriate abstentions | No unanswerable recipes attempted | 0 abstentions; no unanswerable-case denominator |
| Diagnostic tool calls | 5 total, includes 3 bootstrap reads | **5** total; mean 5/3; two model-selected reads |
| Appropriate executed diagnostic reads | Same target-scoped reads | **5/5** under unchanged rubric |
| Required tool coverage | Not achieved | **0/3**; the incomplete runs never read the required dependency/metrics combination |
| Remediation proposal correctness | No proposals | Unavailable, **0 proposals** |
| Failures / timeouts / exclusions | 3 failed run statuses, including one `MODEL_TIMEOUT`; 0 excluded | **3 failures / 0 timeouts / 0 excluded** |
| Unauthorized actions / observable action effects | 0 / 0 | **0 / 0**, three diagnostic runs; no approved-action denominator |
| Graph latency p50 / p95 | 15,109 / 17,234 ms | **26,875 / 45,109 ms**, nearest-rank over three attempts |
| Reported tokens | Partial 7,583 input / 1,087 output | Partial **7,501 input / 1,255 output** from five successful responses; three rejected responses supplied no usage |
| Actual HTTP outcomes | 4×200, 1×429, 2 without status | **5×200, 3×400**, zero 429 |
| Estimated full-run API cost | Unavailable | Unavailable for all three incomplete-usage attempts |

Published model list prices are $0.80/million input and $4.00/million output tokens.
The observed successful-response tokens have a **partial list-price equivalent
of $0.0110208** after repair. That excludes missing usage and is not an invoice,
complete-run cost or assertion that the account is on a paid tier. Free Plan was
requested, billing tier/invoice unverified, no upgrade or provider fallback occurred.
Across before and after, 15 transport attempts yielded nine HTTP 200 responses,
three HTTP 400, one HTTP 429, and two without a response status. Reported tokens
total 15,084 input / 2,342 output, with partial list-price equivalent **$0.0214352**;
six attempts lack usage. This still does not establish total cost.

Latency includes client pacing and graph execution, excludes environment startup
and cleanup, and measures failed work. This is not a speed or quality improvement
claim. The model, prompts and message contracts changed between historical/debug
attempts, while pacing also differs. Repeated calibration incidents are dependent;
the existing machine rubric emits intervals/bootstrap fields, but those are not
interpreted as independent held-out confidence estimates here.

The original scorer/labels and release thresholds remain unchanged. Correctness
and task-completion gates **FAIL**; unsupported and complete-cost gates are
**UNAVAILABLE**. Latency and zero-diagnostic-effect gates pass on the limited
observations. Full benchmark sample-size and recovery gates remain unmet or
unavailable; these diagnostics do not establish model-driven recovery.

## 8. Five-case evaluation gate

**NOT RUN — initial gate failed 0/3.** Planned calibration categories remain
straightforward, dependency, misleading history, ambiguous, and insufficient
evidence. No unseen held-out or larger-benchmark claim is made. The existing v1
held-out contamination remains as documented in Stage 9. No failed case was
automatically repeated until success, and no more real-model calls were made
after the repaired three-attempt sequence.

## 9. Regression and security verification

Initial affected tests: **43 passed / 3 skipped**. Pre-live pipeline tests:
**52 passed / 3 skipped**. These include repeated tests and are not summed as
unique coverage. The three skips were two PG variants when no test URL was supplied
and the separately opted-in main-stack real-model smoke.

The later dedicated-PG regression selection passed **85 tests / 1 skipped**,
zero failures/errors, **12.71 seconds**. It exercised agent contracts, real MCP
fixture investigations, Groq negative contracts, Stage 9 grounding, Stage 7
boundaries, evaluation scoring and release hygiene. The only skip was the optional
main-stack real-model smoke; the actual isolated Groq runs above are separately
recorded. [Selected regression report](../evaluations/reports/stage9-operations-20261108T061229Z-eadd47.json).

Final expanded lifecycle tests: **16 passed**, **3.49 seconds**. They cover a full
mocked HTTP-model graph to supported fixture recommendation, actual ID/result
pairing, JSON state round-trip, substituted target/arguments/request IDs/evidence,
duplicate IDs, fabricated well-formed citations, malformed/empty/refused/truncated
responses, single-attempt 429 handling, and pacing-budget exhaustion. They are
**deterministic/mocked regressions, not successful real-model investigations**.

The separate approval/recovery selection passed **33 tests / 9 skipped**, zero
failures/errors, **124.85 seconds**. All nine skips were SQLite variants of
PostgreSQL durability guarantees. Real PostgreSQL variants exercised changed
arguments/run rejection, raw-resume approval bypass, signed grants with actions
disabled, unauthorized/cross-service requests, expired and other invalid approvals,
approved-action replay, uncertain-timeout reconciliation, and hard process crash
recovery. These use deterministic inputs and actual sandbox effects, not LLM
remediation. [Security/recovery report](../evaluations/reports/stage9-operations-20261108T061517Z-bc8270.json).

Human approval remains mandatory: the model has a read-only
MCP credential, cannot call an action or approval API, and every remediation
contract requires `human_approval_required=true`. PostgreSQL checkpoint and atomic
idempotency implementations were not modified.

## 10. Credential and repository protection

`.groq.env` exists locally and was neither edited nor displayed. `.gitignore` and
`.dockerignore` both include `.*.env`; release scanning excludes the private file
and checks public candidates against configured secret literals and Groq patterns.

Actual requested Git checks (`git check-ignore -v .groq.env`,
`git ls-files --error-unmatch .groq.env`) and `git rev-parse --git-dir` all exited
128: this directory is **not a Git repository**. There is no usable index/staged
diff to inspect, so tracking/staging verification is **unavailable**, not a claimed
Git-ignore PASS. No repository was initialized. Before any future release, verify
ignore/tracking in the actual repository; a tracked credential would be a release
blocker. [Presence-only check](../artifacts/stage9b/credential-scope-check.json).

The release candidate scan passed on **245 files**, with zero findings, including
configured secret literals. The final bounded private-evidence scan and
historical-integrity checks are recorded with the verification results. No
credential was deliberately included in model context or provider error logs;
scanning is bounded text checking, not universal DLP. No unrelated database,
container, volume or project was
reset; only fresh UUID test schemas and their explicitly selected simulated
fixtures were used.

The private scan checked **20 new artifact/report files**, finding no configured
secret literals or 24-character prefixes. All 53 previously snapshotted files
matched except the three intentionally edited core agent modules; historical
reports, dataset labels and lockfiles matched. The preliminary audit flagged those
same intended changes because of Windows path separators; the retained final
audit normalizes paths before comparison. README/report links resolved.
[Final verification](../artifacts/stage9b/verification-final.json),
[candidate scan](../artifacts/stage9b/release-hygiene-final.json).

Only the dedicated review database was stopped at completion. Docker inspection
confirmed `exited` and retained volume `opspilot-stage7_stage7-data`; no volume was
deleted. The five-phase CLI was also exercised against the failed initial report:
it rejected the request before credential loading, environment startup or model
calls. No five-case investigation was launched by that negative gate check.

## 11. Reproduction commands

These are explicit new verification runs, not an automatic retry loop:

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --pull never --wait review-db
.\.venv\Scripts\python.exe -m scripts.verify_stage9b --phase initial
# Five phase requires --initial-report referencing a genuinely passed initial run.
# The recorded Stage 9B initial report did not pass.
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

The verifier loads the private key itself and chooses the explicit Groq profile.
The reusable backend adapter can also be explicitly configured with provider
`groq`, the exact model/base URL above and a server-only key. No frontend credential
or dashboard setting was changed. A profile default is not proof that the dashboard
has been configured for genuine model execution.

## 12. Remaining blockers and verdict

**CONDITIONAL; requested diagnosis reliability is not achieved.** Real call/result
attribution and citation inventory binding are demonstrated, including a valid
real assessment. This is progress in the response pipeline, not a successful
incident diagnosis. Exact preview-provider JSON/tool-generation failures remain
unresolved, and strict mode has not supplied the reliability advertised for these
requests. Model refusal, empty output, truncation and quota states now fail safely;
none is converted into fixture output or silently repaired JSON.

Remaining: accepted factual diagnosis and remediation; reliable structured/function
generation within existing budgets; five-case coverage and proposal grading;
independent semantic assessment of prose claims; a clean held-out study; complete
usage/billing evidence; and genuine-model approved-action/recovery validation.
Original Stage 9 database setup timeouts are not newly resolved by these checks.

No PASS claim is justified by valid JSON, a correctly cited hypothesis or passing
mock tests. Stop after Stage 9B verification, retaining all failures. No Git commit,
push, deployment, frontend feature, dependency upgrade, paid fallback or autonomous
remediation was performed.
