# Stage 9C — Groq provider comparison

18 November 2026 · Windows / Python 3.12.3 · `D:\Projects\OpsPilot-AI`

**CONDITIONAL.** GPT-OSS 20B completed a real MCP health call and correctly used
its result. Qwen's equivalent tool-generation request failed. Both models failed
the separate strict diagnosis probe, so **neither qualified for the three-incident
comparison**. No full investigations were attempted; their diagnosis accuracy is
unavailable. No default model was changed.

Measured evidence: [comparison summary](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/comparison-summary.json),
[complete report](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/report.json),
[request ledger](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/requests.json).
The earlier [transport failure](../evaluations/reports/stage9c/20261118T112300Z-7df4e1/report.json)
is retained and its request is included in the same global budget.

## Verified models and API contract

Both exact identifiers appeared as active in the authenticated model list and
returned successful basic completions. No substitution or fallback occurred.

| Item | Qwen 3.8 27B | GPT-OSS 20B |
|---|---|---|
| Exact identifier | `qwen/qwen3.8-27b` | `openai/gpt-oss-20b` |
| Availability | Active; completion HTTP 200 | Active; completion HTTP 200 |
| Context / maximum completion | 131,072 / 16,384 tokens | 131,072 / 65,536 tokens |
| Tool calling / named tool choice | Documented; this probe failed generation | Documented; actual call passed |
| Choice settings | `auto`, `required`, `none`, named function documented | Same |
| Strict JSON Schema | Documented; diagnosis request failed | Documented; diagnosis request failed |
| Supported reasoning effort | `none`, `default`, `low`, `medium`, `high` | `low`, `medium`, `high` |
| Comparison effort | **`medium`** | **`medium`** |
| Reasoning suppression | `reasoning_format="hidden"` | `include_reasoning=false`; `reasoning_format` unsupported |
| Advertised uncached input / output price per million tokens | $0.80 / $4.00 | $0.075 / $0.30 |
| Observed account quota headers | 1,000 request / 8,000 token limits | Same |
| Published Free Plan limits | 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD | Same |

Sources: [Groq Qwen specifications](https://console.groq.com/docs/model/qwen/qwen3.8-27b),
[Groq GPT-OSS specifications](https://console.groq.com/docs/model/openai/gpt-oss-20b),
[reasoning settings](https://console.groq.com/docs/reasoning),
[strict JSON support](https://console.groq.com/docs/structured-outputs),
[tool-choice behavior](https://console.groq.com/docs/tool-use/local-tool-calling),
[account rate limits](https://console.groq.com/docs/rate-limits),
[API parameters](https://console.groq.com/docs/api-reference).
The [official OpenAI model page](https://developers.openai.com/api/docs/models/gpt-oss-20b)
identifies GPT-OSS as an open-weight model. This experiment used Groq hosting;
OpenAI API billing or service limits were not applied.

Documentation support did not translate into reliable diagnosis generation here.
Preview model behavior and provider-side decoding remain part of the uncertainty.

## Configuration and fairness

- Same basic prompts, tool definitions and strict diagnosis schema; temperature 0.2.
- One model request at a time; Qwen then GPT-OSS within each probe.
- `parallel_tool_calls=false` on tool requests; exactly one harmless tool exposed
  in Probe B, `get_service_health`. Named function choice was explicit for both.
- Probe D declared strict JSON Schema with **zero tools**. Tools and strict output
  were never combined in a request.
- Existing 1,600-output-token limit retained for both. Hidden reasoning can consume
  that budget; the same effort label does not imply identical reasoning work.
  Both use the documented `max_tokens` parameter, deprecated in favor of
  `max_completion_tokens` but retained for existing adapter compatibility.
- Per-call deadline 15 seconds; minimum 12 seconds between request starts.
  Planned graph limits remained 8 tools / 14 model calls / 180 seconds total.
- Same five-observation packet collected once through actual MCP for Probe D.
  Both evidence and message/schema SHA-256 values match between models.
- Preselected calibration cases: `op5-001`, `op5-031`, `op5-091` — checkout fault,
  dependency failure and missing telemetry. Labels/seeds stay in the controller.
  No held-out performance or statistical superiority claim is made.

The shared diagnosis evidence packet SHA-256 was
`b902ff7e295a5d249a85d652f5abe9e21ceba7d606b0f6c0829648a6c01f75fc`.
The strict request message hash matched for both models:
`569109caeee20ef05dc4201632b0a5297815fd6d3f655a02e25b39bf03a867fd`.
Request settings differ only where required by each model, including its identifier
and reasoning-suppression field.

The diagnosis schema composes existing `Assessment` and `Recommendation` models.
It preserves root-cause, remediation, uncertainty and approval fields. Additional
local checks mirror the existing graph's citation membership, hypothesis binding,
freshness, corroboration, confidence, service and action-target checks. Existing
validators and grading thresholds were not relaxed. This composition is larger
than a single assessment; no claim is made that all simpler schemas would fail.

## Actual probe comparison

| Metric | Qwen 3.8 27B | GPT-OSS 20B |
|---|---|---|
| A: ordinary response | **PASS**, HTTP 200, nonempty parsed content | **PASS**, HTTP 200, nonempty parsed content |
| B: real MCP tool generation | **FAIL**, HTTP 400 `tool_use_failed` | **PASS**, typed arguments and actual MCP execution |
| C: tool-result continuation | **NOT RUN**, B supplied no valid call ID/result | **PASS**, matching ID and accurate returned values |
| D: strict structured diagnosis | **FAIL**, HTTP 400 `json_validate_failed` | **FAIL**, HTTP 400 `json_validate_failed` |
| Accepted continuation citations | Unavailable, 0 continuation responses | **1/1** reference, `e001`, valid in that probe |
| Accepted diagnostic citations | Unavailable, 0 parsed diagnoses | Unavailable, 0 parsed diagnoses |
| Completed investigations / attempted | **0/0**; three planned cases gated | **0/0**; three planned cases gated |
| Correct root causes / answerable investigations | Unavailable, 0 attempts | Unavailable, 0 attempts |
| Unsupported final diagnoses / emitted | **0/0**, rate unavailable | **0/0**, rate unavailable |
| Appropriate abstentions | Unavailable, no investigation responses | Same |
| API errors / completion requests | **2/3** | **1/4** |
| Model-requested MCP executions | **0** | **1** |
| Full-investigation median/p95 latency | Unavailable | Unavailable |
| API-response median latency | **578 ms**, n=3 mixed successful/error requests | **812.5 ms**, n=4 mixed requests |
| API-response nearest-rank p95 | **3,578 ms**, descriptive only | **2,078 ms**, descriptive only |
| Reported input / output tokens | **24 / 47**, one response | **1,520 / 186**, three responses |
| Missing-usage completion responses | 2 | 1 |
| Known partial estimated cost | **$0.0002072** | **$0.0001698** |
| Accounted cost including conservative reservations | **$0.0314736** | **$0.00210435** |

One forced single-tool probe cannot measure tool selection across the seven-tool
inventory. The five shared packet-collection reads were controller diagnostics,
not model choices. Total MCP reads were **six**: those five plus GPT-OSS's one call.
Continuation citation validity is not final-diagnosis citation accuracy.

API latency above measures HTTP response processing and excludes client pacing.
Probe elapsed times in the raw report include pacing: Qwen A/B/D were
219 / 11,828 / 14,750 ms; GPT-OSS A/B/C/D were
12,578 / 12,516 / 11,812 / 10,500 ms. Samples mix different outcomes and have
three or four observations, so percentiles are descriptive and not a latency SLO
or evidence of one model being faster. Early A/B probes overlapped a targeted
regression run in separate schemas; no speed comparison is justified.

## Real MCP evidence

GPT-OSS generated this actual function call in Probe B:

```json
{
  "id": "fc_5a2a0cdf-d944-4c5d-bca7-9085328c6a99",
  "type": "function",
  "function": {
    "name": "get_service_health",
    "arguments": "{\"service_name\":\"checkout-service\"}"
  }
}
```

Arguments passed the existing strict MCP input schema and exact target check
before execution. The SDK discovered exactly seven reads under an authenticated
read-only identity. The result came from a real simulator workload in the isolated
PostgreSQL schema, with MCP request ID
`75a57ae9-97ee-41fd-9982-a918c46cddd4`.

The original assistant call was followed by a `role=tool` message with the exact
same call ID. Its projected observation was `e001`. The continuation returned:

```json
{"service":"checkout-service","evidence_id":"e001","error_rate":0.9,"worker_utilization":1.0}
```

Those numbers match the actual returned observation. It did not cite an invented
ID. IDs are local to each probe/run: the separate common diagnosis packet uses
`e001` for the incident and `e002` for metrics. They are never mixed between runs.

The separate diagnosis packet contained real incident, metrics, request logs,
dependency observations and deployment configuration projections. Fixture names,
fault IDs, seeds, cause-naming log codes and expected answers were not sent to
either model. Private reasoning and full authentication headers were not recorded.

## Provider errors versus application defects

| Request | HTTP / error | Origin and implication |
|---|---|---|
| First model-list request | HTTP 200, then `DecodingError` | **Application transport defect** in the new harness: `aiter_bytes()` decoded compression, but reconstructed response retained `Content-Encoding`. Fixed by dropping stale compression/length headers. The initial ledger's generic transport classification is superseded by this diagnosis. |
| Qwen B | 400 `tool_use_failed` | Provider rejected generated function call before OpsPilot argument validation/MCP dispatch. Same tool prompt/schema succeeded with GPT-OSS. |
| Qwen D | 400 `json_validate_failed` | Provider rejected the generated structured response before local Pydantic/citation validation. |
| GPT-OSS D | 400 `json_validate_failed` | Same rejection boundary with the identical diagnosis request and a model-specific supported reasoning configuration. |

The compression fix has a regression test with actual gzip-encoded mock response
bytes, verifying exactly one decode. The first HTTP request is retained as request
1, and the successful repeated metadata GET is request 2. This was a metadata
read repeated after a verified application fix; **no failed model generation or
investigation was retried**. Both the initial failure and continued report remain.

The MCP path and tool-result ordering worked for GPT-OSS. That rules out a universal
failure of the local MCP transport. Both models still failed the shared complex
structured-diagnosis path. The evidence does **not** distinguish an interaction
with the schema/prompt/token budget from provider/model decoder behavior. A strict
schema flag alone cannot establish factual correctness or reliable generation.
No diagnosis generation was accepted, no citation was silently repaired, and no
verified backend diagnosis defect was bypassed.
Probe D had only system/user messages, so that failure also occurs without prior
tool-call history; incorrect tool-call IDs cannot alone explain it.

Provider error codes, phase, model, HTTP status, tool count, reasoning/schema
settings, safe error origin, latency and any supplied usage are in `requests.json`.
Rejected requests supplied neither accepted output nor usage/finish metadata,
so truncation or the exact malformed syntax cannot be established. Raw failed
generations and reasoning traces were deliberately not retained.

An earlier combined shell command was rejected by automatic review before
execution. Startup and provider calls were then performed through separate,
auditable project scripts. It made no API request and consumed no budget.

## Three-case gate and unchanged grading

| Preselected case | Qwen | GPT-OSS |
|---|---|---|
| `op5-001`: checkout fault | Investigation NOT RUN — probe gate failed | Same |
| `op5-031`: dependency failure | Investigation NOT RUN — probe gate failed | Same |
| `op5-091`: insufficient telemetry | Investigation NOT RUN — probe gate failed | Same |

Case `op5-001` was prepared only to supply the common protocol-probe evidence;
that is not a completed graph investigation. The other two cases were not prepared
or evaluated. All six planned investigation selections remain gated, with zero
root-accuracy, task-completion or abstention denominators. No labels, scorer,
quality gates or historical benchmark results changed. The existing v1 held-out
contamination documented in Stages 9–9B remains.

The maximum of 30 requests would also limit full six-investigation coverage under
the existing multi-node graph; no request budget was increased to force completion.
The actual stopping reason was the failed compatibility gate, not quota exhaustion.

## Cost and rate-limit controls

Actual global use: **9 provider requests** — two model-list GETs and seven
completion requests — against the **30-request maximum**. No 429 occurred. Observed
quota headers matched the 1,000-request / 8,000-token account limits. Requests were
sequential and paced; a 401, 403 or 429 would stop the experiment without retrying.
Stopping also avoids issuing requests during any advertised Retry-After period.

Reported totals: **1,544 input / 233 output tokens** from four successful
completions. The three rejected completions supplied no usage. Known partial
list-price estimate: **$0.000377**. Conservative accounting including reservations
for missing usage was **$0.03357795**, below the $0.50 cutoff. This accounting
estimate uses byte-based input reservations and the fixed output cap; it is not
a verified invoice or mathematical billing guarantee. Full actual cost is unknown.
Cached-input discounts were not assumed. Account billing tier was not remotely
verified; no subscription, paid-service activation or spending setting was changed.

## Isolation, security and regression verification

The comparison client has no database engine, reset/fault function, approval API
or action executor. The separate trusted coordinator used a fresh UUID schema in
the dedicated retained Stage 7 review database. Its existing fixture preparer ran
only there, before model requests. No existing schema or main fixture was reset.
Normal MCP audit writes remained enabled.

Fixture hashes over services, faults, incidents/events, deployments, metrics and
logs matched before and after all probes:
`347a0e091861198d9189259b2281a6d90eda0f1dc9ce119d9a9404211c6de96b`.
No action tool was issued. This confirms unchanged observable fixture state;
an action-ledger query was not separately recorded for the probe-only sequence.
Duplicate-action/recovery guarantees are assessed by the security regression tests,
not inferred as an action success rate from read-only probes.

The model cannot approve or execute remediation. The MCP identity has seven
reads, gateway actions are disabled in this environment, and typed remediation
still requires authenticated human approval outside the model. Unknown tools,
cross-service arguments, fabricated citations and unsupported final conclusions
remain rejected. Persistent approval, PostgreSQL checkpointer and transactional
idempotency code were not changed.

Verification completed so far:

- Affected pre-live regression: **55 passed / 3 skipped**; two PG variants lacked
  a configured test URL, and one optional main-stack model smoke was not opted in.
- Dedicated-PG agent/evaluation/boundary/hygiene selection: **94 passed / 1 skipped**,
  zero failures/errors, **15.39 seconds**. The skip is that optional main-stack model
  smoke; actual Groq probes are recorded separately.
  [Regression evidence](../evaluations/reports/stage9-operations-20261118T112450Z-4362d4.json).
- Final focused comparison contracts: **10 passed**, including the compression
  fix, global request cap, pre-request cost guard, model-specific settings,
  secret-safe recording, cross-service rejection and fabricated citation rejection.
- Ruff lint and formatting passed on changed Python files. These mock/fixture
  tests are explicitly separate from the real provider results above.

The selections overlap; their pass counts are not added as unique coverage.

The separate approval/recovery selection passed **33 tests / 9 skipped**, zero
failures/errors, **204.55 seconds**. The skips were unsupported SQLite durability
variants. PostgreSQL variants exercised human-approval bypass rejection, changed
target/arguments/run binding, disabled actions despite signed grants, invalid and
expired approvals, authorized replay idempotency, uncertain-timeout reconciliation
and hard process recovery. These were deterministic infrastructure tests, not
real-model remediation trials.
[Security evidence](../evaluations/reports/stage9-operations-20261118T112824Z-485746.json).
These targeted checks do not supersede historical full-suite results or unresolved
Stage 9 database setup timeouts.

Credential protection: `.groq.env` was read privately and not edited or displayed.
Git/Docker ignore rules exclude `.*.env`. Actual `git check-ignore`, `git ls-files`
and `git rev-parse` checks returned 128 because the directory has no Git repository.
There is no usable index to inspect; Git tracking/staging verification is unavailable,
not a claimed Git PASS. No repository was initialized or committed.

The first candidate secret scan flagged a synthetic literal in a new test. The
test now generates its marker; the scanner and thresholds were not weakened.
The final scan passed on **261 candidate files**, zero findings. No configured real
credential match was detected, so the synthetic finding did not require key
rotation. The bounded evidence scan checked **17 artifact/report files**, finding
no configured credential literals or 24-character prefixes. All **45 protected
historical files** matched their pre-run hashes, and README/report links resolved.
This is bounded text scanning, not universal DLP.
[Verification record](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/verification.json),
[final candidate scan](../artifacts/stage9c-final-secret-scan.json).

Only the dedicated review database was stopped after verification. Docker
inspection confirmed `exited` and retained volume `opspilot-stage7_stage7-data`.
No volume was removed and no unrelated container was stopped.
[Shutdown evidence](../evaluations/reports/stage9c/20261118T112439Z-f2fef0/shutdown.json).

## Files and reproduction

Modified:

- `opspilot/agent/providers.py`: explicit GPT-OSS Groq support, validated optional
  reasoning effort, model-specific suppression, parallel tools disabled. Existing
  Qwen default effort remains `none`; comparison explicitly requests `medium`.
- `README.md`: latest comparison status and report link.

Created:

- `scripts/compare_groq_models.py`: read-only provider/MCP client, budget ledger,
  probes and independent diagnosis validation using existing schemas.
- `scripts/run_stage9c.py`: isolated fixture coordinator, shared packets, unchanged
  rubric and full-investigation admission gate.
- `tests/test_stage9c_comparison.py`: mocked security/budget/transport contracts.
- This report and new timestamped records under `evaluations/reports/stage9c/`.

No dependency/lock upgrade, frontend change, historical report rewrite, commit,
push, cloud resource or deployment occurred. The active `.next` generated build
manifest was not edited.

PowerShell commands for an explicitly reviewed new experiment:

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --pull never --wait review-db
.\.venv\Scripts\python.exe -m scripts.run_stage9c
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

The actual continued run used `--prior-failed-report` pointing to the retained
pre-model compression failure, so its metadata request stayed in the same budget.
That narrowly scoped option accepts only that metadata failure, not a failed
generation/investigation. Do not use repeated new invocations to conceal failures.

## Preferred model and remaining limitations

**GPT-OSS 20B is the preferred candidate for the next schema investigation** because
it completed the real single-tool and continuation path that Qwen failed. It is
not yet a validated OpsPilot default: both failed diagnosis generation and neither
has a root-cause/abstention score in Stage 9C. Default configuration is unchanged.

No statistical superiority follows from one tool probe. Outstanding work includes
the shared structured-diagnosis failure, evidence-backed final diagnoses, calibrated
abstention, three-case matched graph coverage, complete usage/cost data, semantic
verification beyond ID membership, and a genuinely unexposed held-out study.
Full release quality, latency, cost and recovery gates have not been demonstrated
by these protocol probes. **Final verdict: CONDITIONAL. Stop after Stage 9C.**
