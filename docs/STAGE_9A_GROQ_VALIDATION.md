# Stage 9A — Groq connection and first real investigation attempts

8 November 2026 · `D:\Projects\OpsPilot-AI`

**CONDITIONAL — genuine model execution and model-selected MCP reads demonstrated;
the complete investigation smoke gate did not pass.** Five-case investigations and
the larger benchmark remain unrun. These results do not establish deployment or
demo readiness.

This is a dated continuation of [the original Stage 9A readiness report](STAGE_9A_REAL_MODEL_UNBLOCK.md).
That historical report, previous evaluations and dataset labels remain intact.
The user selected a free hosted provider and saved a Groq key locally. No local
runtime, weights, paid fallback, account upgrade or cloud resource was installed
or created. Earlier hardware findings and unresolved Stage 9 setup-timeout findings
remain applicable; this report does not claim to resolve them.

## Provider and credential handling

Provider: Groq OpenAI-compatible Chat Completions, exact endpoint
`https://api.groq.com/openai/v1/chat/completions`. Exact model:
**`qwen/qwen3.8-27b`**, an active preview model returned by the authenticated models
API. Groq documents [tool use and JSON schema output for this model](https://console.groq.com/docs/model/qwen/qwen3.8-27b)
and lists it under [strict structured-output support](https://console.groq.com/docs/structured-outputs).
The observed failures below take precedence over advertised compatibility.

The API key is read privately from process `GROQ_API_KEY` or `.groq.env`. The latter
is excluded by Git and Docker ignore rules. It is never placed in CLI arguments,
provider-response logs or reports. The verifier restricts outbound inference to
the exact endpoint/model, disables ambient HTTP proxy settings and redirects,
uses zero transport retries, disables remote LangSmith tracing, and provides no
fixture or alternate-model fallback. Only projected fictional simulator evidence
is sent to Groq. This is hosted inference, not local-only processing.

An initial models-list request using urllib returned HTTP 403; the explicit httpx2
transport subsequently returned HTTP 200. The precise cause of that transport
difference is unproven. The credential itself authenticated successfully.

Observed quota headers advertised **1,000 requests and 8,000 tokens** for the
provider's quota windows. No 429 occurred in these attempts. The account billing
tier and invoice cannot be verified by these responses. Free Plan was requested;
there was no upgrade or paid fallback. Cost remains **unavailable**, not an asserted
zero-dollar invoice.

## Actual real-model results

All raw evidence is retained in ignored `artifacts/stage9a/` directories. The
[machine-readable aggregate](../evaluations/reports/groq-validation-20261108-initial.json)
records requests, source fingerprints, tool arguments, usage and denominators.
These are sequential debugging attempts with changing contracts on **one
calibration recipe**, not three independent benchmark samples.

| Attempt / artifact directory | Actual result |
|---|---|
| `groq-20261108T053442Z-b360e7` | Connection contract probe: HTTP 400, `json_validate_failed`; required fields absent |
| `groq-20261108T053624Z-f052e2` | Same contract probe failure; preserved separately |
| `groq-20261108T053716Z-18437e` | Real triage contract probe passed: HTTP 200, 457 input / 115 output tokens; no incident or MCP calls |
| `groq-20261108T054000Z-1ecf1f` | Real investigation: model chose metrics; assessment HTTP 400 `json_validate_failed`; failed safely |
| `groq-20261108T054153Z-c7b465` | Real investigation: model chose health; assessment was valid JSON but cited prose instead of IDs; grounding rejected it |
| `groq-20261108T054320Z-a4d0ef` | Real investigation after stricter citation contract: planning HTTP 400 `tool_use_failed`; failed safely |

A separate assessment-contract diagnostic replayed the first attempt's retained
real observations, without running a new incident or new MCP tool. It also returned
HTTP 400 `json_validate_failed`. Its safe metadata is in
`artifacts/stage9a/groq-assessment-contract-20261108T0542.json`. Raw failed generations
and private reasoning are not retained. No successful response was fabricated or
substituted for a rejected response.

### MCP evidence path

Each investigation used the existing LangGraph `Investigation`, the real MCP
protocol/client/server, an independent authorization backend, and a fresh migrated
schema on the dedicated PostgreSQL review database. The model identity exposed
exactly seven read tools; actions were disabled. Initial `get_incident` is a graph
bootstrap read, **not a model-selected diagnostic**.

First investigation:

```json
{
  "tool": "get_service_metrics",
  "arguments": {"service_name": "checkout-service", "limit": 5, "offset": 0},
  "evidence_ref": "e002"
}
```

Second investigation:

```json
{
  "tool": "get_service_health",
  "arguments": {"service_name": "checkout-service"},
  "evidence_ref": "e002"
}
```

Both were actual successful model-selected MCP calls. Subsequent model decisions
received `e001` and `e002`, with context hashes and validated outputs recorded.
For example, the second health observation contained **30 requests, 27 errors,
error rate 0.9, p95 latency 100 ms, worker utilization 1.0 and DB utilization 0.0**.
The assessment referenced those measurements but also misstated 27/30 as 93% and
placed explanations in citation arrays. That response was rejected; its speculative
hypotheses are not an accepted diagnosis.

The initial fault recipe, seed, expected mechanism and case family were available
only to the isolated fixture controller, not included in the model prompt or
projected MCP evidence. Report/controller case IDs are not agent instructions.

**Diagnosis: none accepted. Proposed remediation: none accepted.** The agent
returned no actionable recommendation. Zero action execution records were present
in each isolated schema; no approvals or state-changing MCP calls were attempted.
This limited observation is not a general security certification.

## Measurements and gates

| Metric | Observed denominator and result |
|---|---|
| Completed supported investigations | **0/3 attempts**, one distinct answerable calibration recipe |
| Failed / validation abstentions | 2 failed; 1 invalid-decision abstention; not a correct uncertainty abstention |
| Timeouts / excluded attempts | 0 / 0 |
| Correct root identification | 0/3 answerable attempts; no accepted diagnosis |
| Unsupported diagnosis rate | Unavailable: 0 diagnoses; rejection is not a 100% accuracy result |
| Appropriate executed diagnostic reads | 5/5 reads under the existing relevance rubric; includes three bootstrap reads |
| Successful model-selected reads | 2; both reached the subsequent model context |
| Correct abstention rate | Unavailable: no unanswerable recipes attempted |
| Remediation proposal correctness | Unavailable: no accepted proposals |
| Graph latency per attempt | 5,016 / 4,454 / 2,063 ms; p50 **4,454 ms**, p95 **5,016 ms**, nearest-rank |
| Action effects | 0 across 3 read-only investigations |
| All inference/contract HTTP requests | **12**: 7 HTTP 200, 5 HTTP 400; models-list requests excluded |
| Reported usage across these requests | **8,052 input / 1,479 output tokens**, incomplete: five rejected requests supplied no usage |
| Estimated API cost | Unavailable; billing tier/invoice unverified |

Latency excludes environment startup/cleanup and reflects failed/abstained graph
execution, not successful task latency. Small, dependent debugging attempts do not
justify confidence intervals, superiority comparisons or generalization claims.
No retry was hidden inside an attempt; every separate invocation is retained.

The complete smoke gate remains **FAIL**. Five-case coverage is **0/5** and the
up-to-30 benchmark is **NOT RUN**, as required when the smoke does not pass.
The v1 held-out contamination described in the historical report also remains;
replaying that split could only establish regression/exploratory performance.
No quality threshold, action policy, expected label or investigation budget changed.

## Implementation changes and verification

- `opspilot/agent/providers.py`: include the exact output schema in model messages,
  separately from untrusted context; explicitly require JSON/function arguments and
  bare evidence IDs. Existing response validation and grounding remain enforced.
- `opspilot/agent/schemas.py`: constrain hypothesis/root/remediation citations to
  observation-ID syntax. Unknown but syntactically valid IDs still fail the existing
  independent membership checks.
- `scripts/verify_groq.py`: explicit probe/smoke/five modes, bounded requests and
  safe usage/error recording, real MCP/PG isolation, benchmark gate and no actions.
- `tests/test_groq_contracts.py`: mocked contract, citation, endpoint/model scope
  and secret-safe failure regressions. These tests are not LLM evaluations.
- `scripts/release_hygiene.py` and `tests/test_release_hygiene.py`: detect Groq-shaped
  credentials without needing an installed local secret; test `.groq.env` exclusion.
- This report and the new dated aggregate; private credential/evidence files stay
  excluded from release assets. Dependencies and lockfiles were not changed.
- `README.md`: replace the obsolete zero-real-calls status with these measured
  initial attempts; keep earlier stage findings explicitly historical.

After the citation/contract changes, the selected PostgreSQL/MCP/agent/evaluation
regression run passed **48 tests, 1 skipped, zero failures/errors** (16.45 seconds).
The skip is the existing separately opted-in main-stack real-model pytest; actual
Groq execution above used the isolated verifier and is reported separately.
[Regression evidence](../evaluations/reports/stage9-operations-20261108T054242Z-d068f9.json).
The later release-hygiene regression passed **14/14 tests**. Ruff checks passed on
changed Python files. Earlier adapter regressions passed 36 tests with three
explicit skips; these repeated checks are not added together as unique coverage.

The separate durable-execution/MCP regression passed **98 tests, 25 skipped, zero
failures/errors**, in **330.77 seconds**. The skips are the intentionally unsupported
SQLite variants of PostgreSQL checkpoint, locking and role-privilege guarantees;
corresponding PostgreSQL variants were exercised, including the previously
affected expired-approval case. This suite uses deterministic model inputs, real
MCP and PostgreSQL; its passes are not evidence of LLM diagnosis quality.
[Approval/recovery regression evidence](../evaluations/reports/stage9-operations-20261108T054452Z-89595c.json).

The final release scan passed on **238 candidate files**, with zero findings, including
checks against configured secret literals. The private-evidence check scanned
**21 new Groq artifact/report files**, with no matching configured secret literals
or 24-character prefixes. This is bounded text scanning, not universal DLP.
Local report/README links resolved. Only the dedicated review DB was stopped
after verification; its retained `opspilot-stage7_stage7-data` volume was preserved.
The 45-file prior integrity snapshot showed only the intentionally changed provider
adapter differed; protected historical reports, dataset files and locks matched.
[Final verification](../artifacts/stage9a/groq-final-verification-20261108.json) and
[final release scan](../artifacts/stage9a/groq-release-hygiene-final-20261108.json)
retain the details.
No clean full-suite claim supersedes the historical
301-pass/49-skip/two-setup-error Stage 9 run.

## Reproduction and remaining work

From the project in PowerShell, with the existing `.stage7.env` and private Groq
key saved locally:

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --pull never --wait review-db
.\.venv\Scripts\python.exe -m scripts.verify_groq --phase probe
.\.venv\Scripts\python.exe -m scripts.verify_groq --phase smoke
# Five-case mode requires --smoke-report pointing to a passed real smoke report.
# Do not run it against the failed reports above.
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

The verifier reads the key itself and creates fresh evidence directories. These
commands make real hosted model calls and consume the account's quotas. They do
not configure the dashboard's backend provider automatically. No large model,
local inference runtime, frontend change, commit, push or deployment is required.

Outstanding: reliable structured decisions and function calls from this exact
preview model; a complete grounded diagnosis/remediation; five-case coverage;
an honestly designated benchmark with proposal scoring; real-model security and
durable approved-action validation. Provider/schema failures remain visible rather
than loosening evidence checks or claiming that a working API key proves agent
quality. No model/provider switch occurred during these checks.
