# Stage 9 — real LLM validation and reliability review

Date: 7 November 2026. Project: `D:\Projects\OpsPilot-AI`.

**Verdict: BLOCKED — REAL MODEL UNAVAILABLE.** No genuine model was executed.
This stage audits the implemented agent, fixes two confirmed evidence-handling
defects, and runs explicitly labeled deterministic verification against real
PostgreSQL and MCP. Those results do not establish LLM diagnostic quality,
prompt-injection resistance, model latency, or model-driven recovery.
Reviewed machine-readable results and the full historical/current skip ledgers:
[Stage 9 evidence summary](evidence/stage9-validation.json).

## 1. Provider/model actually used

**None. Zero real-model calls and zero real-model cases.** The process and all
root project environment files contained no provider, model, base URL or API key under
`OPSPILOT_AGENT_*`. Neither `ollama` nor `lms` was on PATH. Bounded discovery requests
to loopback Ollama `11434/api/tags` and LM Studio `1234/v1/models` were unreachable.
No credential value was printed. No model weights were downloaded, paid API called,
or substitute fixture installed under real mode.

The exact blocker is absent inference runtime/model and explicit provider
configuration, rather than a demonstrated incompatibility of a particular model.
The user's instruction permits deterministic-only checks in this situation.
The existing real adapters remain available for later explicit configuration;
adapter contract tests use mocked HTTP responses and are not real-model tests.

Evidence: [configuration presence, endpoints and historical hashes](../artifacts/stage9/20261107T131512Z-d6ae0b/inspection.json).
An actual real-mode CLI invocation also exited **2**, returning `mode=real`,
`status=failed` and an explicit no-fixture-substitution error before any provider
request. This is a missing-configuration boundary check, not a model smoke test;
its 5,359ms process startup/failure duration is not model latency. See
[recorded result](../artifacts/stage9/20261107T131512Z-d6ae0b/real-mode-unavailable.json).

## 2. Hardware and verification environment

| Item | Observed environment |
|---|---|
| OS / native Python | Windows / Python 3.12.3 |
| RAM | 14,903,754,752 physical bytes, approximately 13.88 GiB |
| Free RAM | Approximately 6.58 GiB before Docker; 4,102,576 KiB during verification |
| CPU | Windows reported one logical processor |
| NVIDIA GPU | GeForce GTX 1650; 4,096 MiB VRAM; 3,923 MiB free at snapshot |
| Project drive | 22,005,653,504 free bytes at snapshot, approximately 20.49 GiB |
| Docker Engine | 29.9.2; Docker Desktop was initially stopped and was started locally |
| Database | Dedicated retained Stage 7 review PostgreSQL 18.6, loopback port 56437 |
| Isolation | New UUID schemas only; no main simulator fixtures or historical databases reset |
| Locked agent stack | LangGraph 1.2.19, PostgreSQL saver 3.2.0, MCP SDK 2.3.0 |
| Dashboard | Existing Next.js 16.4.4 / React 19.3.1 / TypeScript 7.0.2 |

See [hardware snapshot](../artifacts/stage9/20261107T131512Z-d6ae0b/hardware.json)
and `uv.lock` / `frontend/package-lock.json`. These resources do not establish that
a suitable tool-calling model fits its required 16,384-token local context. That
would require testing a specific model/runtime. No download was justified for this
verification-only task. Host contention also limits latency comparisons.

## 3. Capability matrix: implementation versus demonstrated reasoning

Inspected Stages 1–8 reports, architecture, workflow/providers, MCP contracts/server,
evaluation subjects/scorer/controller, approval policy, durable graph/checkpointer,
dashboard job manager and tests. The crucial distinction is the supplied
`DecisionModel`, not the presence of a graph or a function named “agent.”
Currently **no real LLM executes any of the seven requested intelligence decisions**
in this environment; the real-mode branches delegate them to the configured model
only when one is explicitly supplied.

| Capability | Actual implementation in configured real mode | Deterministic control / fixture behavior | Demonstrated with a genuine model here? |
|---|---|---|---|
| Incident triage | Model frames hypotheses from incident observations | Initial `get_incident` is compulsory code | No |
| Diagnostic selection | Model emits a typed function call selecting a read-only MCP diagnostic | Executor validates allowlist, identity/scope, arguments and budgets; fixture uses a fixed order | No |
| Evidence interpretation | Model assesses projected measurements and cites observation IDs | Projection strips fixture truth; response/resource validation is code | No |
| Multi-step planning | Model chooses further investigation or proposal/abstention via typed outputs and conditional routing | Graph edges and stopping limits are programmed | No |
| Alternative hypotheses | Model supplies alternatives, supporting and contradicting evidence | Validators check references and minimum corroboration; cannot prove semantic correctness | No |
| Root cause | Model proposes a cited explanation after evidence assessment | Fixed minimum confidence/freshness/corroboration gates; baseline uses thresholds | No |
| Remediation | Model proposes one named sandbox action or manual investigation | No model credential grants action authority; evidence/action scope enforced in code | No |
| Abstention | Model can explicitly abstain or request more evidence | Validation errors, missing grounding and exhausted budgets also stop the workflow | No |
| Final recommendation | Typed validated decisions assembled into a structured record | Final assembly is deterministic, not an extra model reasoning step | No |
| Approval/execution/verification | Separate human approval and deterministic durable executor | Transactional authorization, idempotency, measured workload and fixed verification policy | Infrastructure tests only |

Sources: `opspilot/agent/{providers,workflow,evidence,fixtures,schemas}.py`,
`evaluations/runners/subjects.py`, `opspilot/durable/`, `opspilot/dashboard/jobs.py`.
`FixtureDecisionModel` performs no inference. The baseline is a fixed five-tool
threshold classifier. Neither is evidence that a real LLM chose an appropriate tool.

Real provider support is explicitly `openai-compatible` HTTP Chat Completions or
local native `ollama`. Planning uses a real function-call schema; other stages use
structured JSON validated by Pydantic. Missing configuration, failed HTTP, malformed
outputs and timeouts fail explicitly; there is no real-to-fixture fallback.
Endpoints must be trusted operator configuration. No provider endpoint was newly
certified compatible in this stage.

## 4. Real end-to-end incident and evaluation sample sizes

The requested genuine checkout investigation **could not run**. Model ID/version,
real diagnostic arguments/responses/decision steps, diagnosis/citations, remediation,
latency, tokens and cost are unavailable. They are not replaced with a fixture
transcript. No real diagnosis was submitted for human approval.

The fresh before-change report selected the original 40 held-out recipes for each
arm. The rules arm attempted 40; each real arm excluded all 40 with
`REAL_MODEL_UNAVAILABLE`. Thus **80 excluded real-arm selections, zero attempted
real cases, zero matched genuine-model comparisons**. The 30-case real-model target
was not met. No real calibration or genuinely unseen held-out evaluation occurred.

Separate new reports, preserving every historical result:

| Track | Sample | Execution |
|---|---:|---|
| Rules calibration, before / after | 20 each | Five real MCP reads per incident, no inference |
| Rules historical held-out regression replay, before / after | 40 each | Real MCP/PostgreSQL, no inference |
| Explicit structured fixture calibration plumbing | 6 | LangGraph + actual MCP, deterministic decisions |
| Real arm B / real arm C | 0 attempted each; 40 excluded each | No provider calls |

For the requested Stage 9 comparison: **A = rules, B = deterministic fixture,
C = genuine LLM (unavailable)**. Historical JSON arm names are retained for
compatibility: `baseline` is rules; `structured` can run either explicit fixture
mode or real mode; `llm` is a separate direct real-model comparator. Always read
`mode` alongside `arm`. The six fixture trials and 40-rule replay are different
sample sizes, so no matched superiority comparison is claimed.

These are 126 deterministic trial executions over 60 distinct recipes, with
repeated cases; not 126 independent or real-model evaluations. Fixture cases are
calibration only. After inspection/tuning, the old held-out split is a **regression
replay**, not a new unbiased held-out score. A later real-model study needs a newly
sealed split and a calibration-first protocol; v1 cannot be advertised as unseen.

Reports: [calibration before](../evaluations/reports/stage9-calibration-before.json),
[calibration after](../evaluations/reports/stage9-calibration-after.json),
[replay before](../evaluations/reports/stage9-heldout-before.json),
[replay after](../evaluations/reports/stage9-heldout-after.json),
[fixture calibration](../evaluations/reports/stage9-fixture-calibration.json).
Each has a pre-execution plan and source/lock/dataset hash. Formatting-only changes
between some plans change hashes without changing thresholds; the plans are retained.
All trials, failures, exclusions and fixed limits remain in their reports.

## 5. Root-cause accuracy, unsupported diagnosis and tool selection

The scorer, dataset, answerability labels and release thresholds were **unchanged**.
Accuracy counts abstention/timeout/failure as incorrect on answerable cases. Task
completion counts correct abstentions on unanswerable/healthy cases as success.
Unsupported rate uses emitted diagnoses as its denominator, including diagnoses
on cases labeled unanswerable; a wrong grounded answer is a correctness error.
Tool relevance uses the frozen case rubric, not a retrospective LLM judge.

| Rules metric | Calibration before | Calibration after | Replay before | Replay after |
|---|---:|---:|---:|---:|
| Root cause / answerable attempts | 11/13 (84.62%) | **10/13 (76.92%)** | 24/26 (92.31%) | 24/26 (92.31%) |
| Task completion / attempts | 17/20 | 17/20 | 36/40 | 38/40 |
| Unsupported / diagnoses | **1/14 (7.14%)** | 0/12 | **2/28 (7.14%)** | 0/26 |
| Relevant tools / calls | 78/100 | 78/100 | 174/200 | 174/200 |
| Required-tool coverage / cases | 20/20 | 20/20 | 40/40 | 40/40 |
| Abstentions / attempts | 6/20 | 8/20 | 12/40 | 14/40 |
| Timeouts / attempts | 0/20 | 0/20 | 0/40 | 0/40 |

**Calibration correctness now FAILS the existing 80% gate.** The conservative
ambiguity rule adds an abstention on inventory dependency case `op5-037` as well
as the intended ambiguous case `op5-109`. This coverage tradeoff is retained rather
than hidden by changing labels or thresholds. The replay's observed unsupported
rate passes its unchanged ≤5% gate, but 0/26 has a Wilson 95% interval of
0–12.87%; it does not establish a low population failure rate. Replay root accuracy
has a descriptive Wilson interval of 75.86–97.86%, task success 83.50–98.62%.
Families share mechanisms and variants, so these are finite-suite descriptions,
not production confidence guarantees or evidence of agent superiority.

Appropriate abstention on expected-abstention/healthy cases improved from **6/7
to 7/7 calibration** and **12/14 to 14/14 replay**. The calibration-after run also
abstained on **1/13 answerable cases**; replay-after had **0/26 answerable
abstentions** and two wrong diagnoses. Rules do not emit remediation proposals,
so a correct-remediation-proposal rate is not applicable to that arm. The existing
diagnostic fixture report maps actions to mechanisms but does not separately
persist/grade proposal correctness. No separate proposal-quality percentage is
invented; the genuine-model measure is unavailable. Action execution/verification
tests below measure infrastructure behavior, not the quality of model proposals.

The six fixture trials have root/task success **3/6**, unsupported **0/5 diagnoses**,
one abstention, zero timeouts, 28/35 rubric-relevant calls and required coverage
6/6. Two wrong diagnoses still exist. These deliberately limited threshold
fixtures establish workflow plumbing, not LLM quality. No fixture/rule scores are
combined with real scores, and real accuracy/tool selection/unsupported rate are
**unavailable (0 denominator)**.

## 6. Investigation of the historical 7.14% failure and fixes

All six historical unsupported cases came from **arm A, mode `rules`**, zero model
calls: calibration `op5-109`, development `op5-110`–`op5-112`, held-out
`op5-113`–`op5-114`. The last pair produces the reported **2/28 = 7.14%**.
All belong to `failed_remediation`: local checkout worker saturation plus payment
unavailability. The frozen rubric intentionally expects abstention for multiple
possible roots. The baseline selected payment dependency failure and set
`evidence_supported=true` using `e002/e003/e004`. It discarded the local resource
signal when it switched its metric variable to the downstream metric.

This is a **baseline ambiguity/uncertainty failure**, not a measured LLM hallucination.
The “supported” flag was only a minimum evidence-presence check, not proof of a
unique cause. The frozen evaluator correctly flags the unanswerable-case diagnosis;
the gate was not weakened. Known dependency failure alone is observable, but does
not establish the unique root cause of all checkout symptoms in this recipe.

A separate calibration reproduction used actual MCP projected responses:
checkout worker utilization **1.0**, error rate **1.0**, p95 **100ms**, statuses
**2×502 + 31×503**; payment degraded with worker utilization **0.102823**.
The baseline still returned payment/dependency-unavailable. See
[captured operational observations](../artifacts/stage9/20261107T131512Z-d6ae0b/ambiguity-before.json).
No private fault labels were passed to the subject.

Two minimal fixes in `evaluations/runners/subjects.py`:

1. Pass the original validated arguments to `parse_response` in shared reads and
   the direct LLM comparison arm. Schema-valid service/incident/topology
   substitution is now rejected, matching the main investigator's existing rule.
2. Abstain when a degraded dependency coexists with local pool saturation or local
   worker pressure/error evidence. Reuses existing thresholds, has no case IDs,
   fault metadata, split names or answer labels in its decision logic.

Deterministic regressions reproduced **3 failures / 1 passing control before**
the fixes. The immediate affected regression passed **16 tests / 1 PostgreSQL
environment skip**. The full PostgreSQL run below includes that skipped case.
Scorer/labels/thresholds and all old research records remain preserved. The
original failed gate was rerun both before and after, not inferred from unit tests.

## 7. Safety: unsafe proposal versus prevented execution

No genuine-model safety trial occurred. Whether a real model follows malicious
logs, proposes unsafe actions, over-calls tools or tries to approve itself remains
unverified. A gateway denial would establish a successful boundary, not a safe
model proposal; those outcomes must be recorded separately in future studies.

The deterministic/security regression exercises these independent boundaries:

| Threat | Expected infrastructure behavior | Evidence source |
|---|---|---|
| Model/client self-approval | No human grant from resume values or model text | `test_raw_resume_value_cannot_create_human_approval`, operator authentication tests |
| Read-only caller invokes a write | Permission denial; zero committed effects | MCP and measured operational security tests |
| Modified arguments, target or run | Exact intent/fingerprint/resource checks reject it | `test_approval_cannot_authorize_changed_arguments_or_run`, action binding tests |
| Expired/revoked/stale approval | No state change | `test_expired_revoked_and_stale_approval` |
| Replayed action / duplicate request | One durable effect; replay denied or reconciled | Duplicate delivery, request ID and action ledger tests |
| Log injection / substituted MCP evidence | Untrusted text projection and resource binding; no extra authority | Real persisted-log MCP test, Stage 7 boundary tests, new Stage 9 substitution tests |
| Action succeeds, service remains unhealthy | Failed measured verification; separate fresh recovery approval required | `test_action_success_but_verification_failure_requires_separate_recovery` |

Test identities are synthetic authenticated operators in isolated schemas, not a
claim that a human attended automated tests. No live human credential or test
approval is exposed to a model. No action tool was added to the investigator.
Diagnostic rules replay had **zero action attempts / 200 calls**, zero observable
effects / 40 cases; it made zero approval decisions or action verifications, whose
rates remain unavailable instead of being called 100% safe.

## 8. Durability and failure recovery

The official PostgreSQL saver persists the **post-investigation execution graph**
under the stable investigation run/thread UUID. Advisory locks serialize resumes.
Sandbox effect, one-use grant consumption and unique action ledger commit atomically.
After uncertain acknowledgment, reconciliation reads the ledger before redelivery.
Checkpointing alone is not treated as exactly-once side-effect delivery.

The full regression includes actual child-process exits before approval, after
approval, and after committed action/before acknowledgment; crash-before-execute;
concurrent approvals/resumes; rejection/expiration/revocation/staleness; uncertain
MCP timeout; interrupted execution; failed remediation/verification; real simulator
process restart; real MCP disconnection; and stop/start of **only the dedicated
review PostgreSQL container** with its volume retained. Existing checkpoint logic
and 90-second hard-process deadlines were not altered to obtain passes.

These are deterministic proposal/decision inputs exercising real infrastructure.
They do **not** prove recovery of a genuine model-originated investigation.
`Jobs.recover()` marks in-flight inference interrupted rather than silently
repeating paid inference. The investigation graph itself is not checkpointed for
resuming an interrupted model call. Action execution is resumable only after the
validated durable handoff. DB corruption, arbitrary remote exactly-once effects,
HA failover and network partition recovery are outside the tested guarantees.

The broad run completed **8/9 operational trials**: five security trials,
two measured hard-process recoveries and one failed-verification/recovery trial.
There were **0 unauthorized effects / 5 security trials**, **0 duplicate effects /
3 replay-or-recovery trials**, **2/2 recorded measured recoveries**, **5/5 measured
verification judgments**, and **4/4 expected policy rejections**. Synthetic inputs
included two unauthorized write attempts and one approval-bypass attempt. These
counts describe successful boundary enforcement, not safe real-model intent.
The missing measured-before-approval recovery trial failed during DB setup; all
operational release gates in that broad report correctly retain **FAIL** for
incomplete coverage.

The separate exact recheck passed that recovery case along with the expired-grant
case and the historical fixture-isolation case: **3 passed, 0 skipped/errors**,
27.49s. It produced a genuine Stage 9 per-node evidence ledger. These results do not
retroactively turn the broad run into a clean pass. A fresh complete operational
file rerun is recorded separately, without pooling partial trials.

That complete operational recheck finished **9 passed / 9 expected SQLite skips**,
94.89s pytest (102.313s launcher), **9/9 recorded PG trials**. It measured
**0 unauthorized effects / 5 security trials**, **0 duplicate effects / 4
replay-or-recovery trials**, **3/3 hard-process recoveries**, **6/6 verification
judgments**, and **4/4 expected rejections**. All five scoped operational gates
passed in [its own report](../evaluations/reports/stage9-operations-20261107T133558Z-6d4ba4.json).
Small-sample uncertainty remains wide: recovery Wilson 95% interval 43.85–100%,
verification 60.97–100%. This is deterministic operational evidence; it does not
change the broad setup errors, calibration failure, or absent real-model gate.

Additional passing broad-run checks: three hard OS-process crash variants and four
injected crash boundaries; expired/revoked/stale approval checks; four changed
action/run/argument bindings; concurrent resume exclusion; concurrent human
decisions yielding one grant; four persisted malicious-log variants through real
MCP (injection present on transport, absent from fixture model context, zero
effects); actual simulator restart preserving incident ID; MCP disconnection
yielding unavailable with zero effects; and actual PostgreSQL restart recovering
the same approval with **one effect and one verification**. Exact test names,
properties and outcomes are in the full JUnit, not inferred from a status label.

## 9. Latency, token and cost accounting

Actual elapsed diagnostic latency excludes fixture generation and human wait.
Mean = sum of attempted trial milliseconds / attempted trials; p50/p95 use the
existing nearest-rank convention. No real latency or billable token estimate exists.

| Track | n | Mean ms | p50 ms | p95 ms | Tool errors / calls |
|---|---:|---:|---:|---:|---:|
| Rules calibration before | 20 | 1,337.50 | 704 | 3,687 | 2/100 |
| Rules calibration after | 20 | 1,048.50 | 672 | 1,688 | 2/100 |
| Rules replay before | 40 | 1,640.13 | 750 | 4,172 | 4/200 |
| Rules replay after | 40 | 1,053.58 | 703 | 2,812 | 4/200 |
| Fixture calibration | 6 | 1,226.50 | 1,031 | 2,046 | 0/35 |
| Genuine model | 0 | Unavailable | Unavailable | Unavailable | Unavailable |

The rule tool errors are deliberate `DOWNSTREAM_UNAVAILABLE` responses in outage
cases. They produce abstention, not guessed service diagnoses. None was removed
from the denominator. Rule replay uses exactly **200/40 = 5 tools/incident**;
fixture calibration uses **35/6 = 5.83**. Latency differences are not a controlled
performance claim; Docker warming and concurrent host work vary. Replay-after p95
bootstrap 95% interval is 1,250–5,235ms, descriptive only.

Rules make zero model calls/tokens and have exactly **$0 model API cost**.
Fixture model token counts are unavailable/not applicable (six missing usage
records), with $0 inference API cost because no inference happened. Unavailable
real arms have unknown cost/usage, not fabricated zero-cost successful runs.
These figures exclude local hardware/energy/hosting costs. Future real runs require
provider usage and explicitly trusted input/output prices; failed requests may
have unknown billable cost.

## 10. Historical skips, setup error and intermittent timeouts

The [complete per-test ledger](../artifacts/stage9/20261107T131512Z-d6ae0b/inspection.json)
classifies **every one of the original 49 regression and 48 Docker skips**, with
node, exact reason, source XML and requested classification. No skipped assertions
are counted as passed.

| Historical suite | Classification | Count / exact explanation |
|---|---|---|
| Native full regression | Expected environment limitation | 46 SQLite variants: 41 durable-PG-only plus controller, row locking, role privileges, row-lock semantics and migration round trip |
| Native full regression | Optional external dependency | 2 opt-in running-main-API checks; 1 opt-in genuine-model smoke |
| Docker portable subset | Expected environment limitation | 47 selected PostgreSQL variants had no dedicated DB URL inside that container |
| Docker portable subset | Optional external dependency | 1 genuine-model smoke |
| Both | Intentionally excluded / unresolved defect among skip reasons | 0 / 0; operational timeout risks are tracked separately |

The Docker subset and full native suite select different tests. Their skip counts
are not interchangeable. Native PostgreSQL verification executes the PG variants;
it does not retroactively make the Docker skips pass. A fresh containerized
DB-connected regression was not claimed in Stage 9.

The historical broad run remains **286 passed / 49 skipped / 1 setup error**:
`test_direct_fault_does_not_modify_other_fixtures[postgres-payment-service-worker-saturation]`.
The preserved traceback ends in Psycopg `ConnectionTimeout: connection timeout
expired` during connection setup, before the test's isolation assertions ran.
The unchanged isolated recheck passed in **7.83s**. This demonstrates that a later
connection succeeded within its deadline; it does not establish why the earlier
connection was late. No server/host timing correlation was retained to distinguish
Docker scheduling, connection startup or transient resource contention. **The
underlying cause remains unresolved.** No blind retries, timeout inflation or
checkpoint modifications were introduced.

The Stage 9 broad run reproduced **two further PostgreSQL connection setup
timeouts**, on `test_measured_hard_recovery[postgres-before_approval_restart]` and
`test_unapproved_actions_fail_closed[postgres-expired]`. Both passed unchanged in
the focused three-case recheck, including the old historical failing case. Again,
this establishes later availability, not the underlying reason for earlier delay.
Current PostgreSQL logs show a **192.468s checkpoint** (74.071s syncing 10,765
files), consistent with possible storage contention but insufficient to prove
causality. [Retained server sample](../artifacts/stage9/20261107T131512Z-d6ae0b/postgres-during-regression.log).
Connection deadlines, checkpoint policy and action security were left unchanged.

Other preserved timing failures: Stage 7's 90-second child recovery timeout later
passed unchanged in 28.66s; Stage 8's broad browser/login timeouts later passed
isolated and final combined tests. Their causes remain unproved. Fresh passes
cannot erase these historical failures or establish a reliability SLO. The prior
missing temporary-parent setup issue was in the launcher, whose current runners
create a fresh parent directory before pytest; it is separate from the PG timeout.

## 11. Current regression and UI verification

| Check | Actual result |
|---|---|
| New adversarial reproductions before fixes | 3 failed, 1 passed; retained XML |
| Immediate affected Python regression after fixes | 16 passed, 1 skipped; retained XML |
| Full PostgreSQL/API/MCP/approval/durable/security regression | **301 passed, 49 skipped, 2 setup errors**, 581.749s JUnit; 591.375s launcher |
| Exact affected + historical-case recheck | **3 passed**, 27.49s; no errors/skips |
| Complete operational file recheck | **9 passed, 9 expected SQLite skips**, 94.89s; no errors |
| Python Ruff lint / format | Passed; 152 Python files formatted at final scope check |
| Frontend TypeScript | Passed |
| Frontend lint | Passed, ten files inspected |
| Release-candidate secret scan | Passed: 229 candidate files, zero findings |
| Bounded private log/report scan | Passed: 30 files, 16 configured secret values/prefixes, zero matches |
| Stage 9 genuine-model smoke / browser | Unavailable / not performed |

Full-run artifacts use `artifacts/stage9/20261107T132234Z-1b41d2/`; JUnit is the
canonical per-node result. **The initial launcher also had a post-test evidence
writer error:** reusing the Stage 7 plugin correctly rejected a Stage 9 output path.
Its `cases.json` was not written; JUnit, logs and eight trial records survived.
A dedicated Stage 9 writer now reuses the hooks with its own project-scoped output
guard and exclusive file creation, preserving the original Stage 7 guard. The
[focused evidence ledger](../artifacts/stage9/20261107T133345Z-48e678/cases.json)
and JUnit verify the correction. This tooling error is separate from the two DB
setup errors and is retained in the original log. It is not a runtime security fix.
Counts from overlapping focused checks are not added to the full-suite total.
Reports record source fingerprints and missing coverage; release readiness stays
false. The fresh 49 skips have the same classified reasons as the historical
native suite; none is called a passing assertion.

The fresh complete operational ledger is at
`artifacts/stage9/20261107T133558Z-6d4ba4/cases.json`. The original broad error report
and both rechecks remain separate in the public evidence summary. No claim of a
clean full-suite run is made.

The UI audit found provider/model identity missing from the workspace display.
The existing snapshot already supplies these values, so the workspace now renders
mode, actual configured provider/model identifier and cost availability from that
snapshot. Existing real tool calls, citations, diagnosis, proposed action, human
approval, execution outcome, measured verification, audit and latency views are
retained. Fixture mode explicitly says no inference; real-mode availability remains
disabled without valid configuration. No credentials are added to browser payloads.

TypeScript/lint verify the small presentation change. **No Stage 9 browser was used
and no frontend build was run**, so this is not genuine-model UI verification.
An older production build will require a build when demonstrating the change;
it was not unnecessarily rebuilt to display nonexistent real-model results.
Historical Chromium evidence remains correctly labeled fixture-only.

## 12. Reproduction and preserved evidence

Run from project root in Windows PowerShell after Docker Desktop is ready:

```powershell
Set-Location D:\Projects\OpsPilot-AI
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --wait review-db
.\.venv\Scripts\python.exe -m reviews.stage9_audit

# Choose NEW filenames; the runner rejects overwriting reports or plans.
.\.venv\Scripts\python.exe -m scripts.review_stage9 -- --split calibration --arms baseline --output evaluations/reports/stage9-new-calibration.json
.\.venv\Scripts\python.exe -m scripts.review_stage9 -- --split held_out --arms baseline llm structured --output evaluations/reports/stage9-new-regression-replay.json
.\.venv\Scripts\python.exe -m scripts.review_stage9 -- --split calibration --arms structured --fixture-smoke --limit 6 --output evaluations/reports/stage9-new-fixture.json
.\.venv\Scripts\python.exe -m scripts.verify_stage9

# Stop only the review database; retain its volume.
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

The wrapper validates container project/service/port identity, constructs the
dedicated test URL privately and disables remote tracing. It does not automatically
load provider keys from dotenv files. Explicit real-provider variables in the
operator's process are respected by the benchmark; do not select real arms until
their inference/billing is intended. Future real runs must be labeled real, retain
safe projected tool arguments/results and structured decision summaries, never
private chain-of-thought or secrets. Use the existing CLI/configuration described
in [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) and [MCP_TOOLS.md](MCP_TOOLS.md).

Historical research report, stage report and dataset hashes were captured before
changes; final integrity comparison is retained with the Stage 9 evidence. Raw
logs/traces, private env files and test credentials stay ignored. New sanitized
benchmark JSON/plan files preserve exclusions, complete metrics and failed gates.
No unrelated container, main database, volume or other project was modified.
The [candidate scan](../artifacts/stage9/20261107T131512Z-d6ae0b/release-hygiene.json)
contains file digests; the separate
[bounded private scan](../artifacts/stage9/20261107T131512Z-d6ae0b/private-log-secret-scan.json)
checks actual configured literals and 24-character prefixes without printing them.
Neither is a universal secret-detection claim. Benchmark source fingerprints cover
Python runtime/evaluation/test code, `uv.lock` and dataset manifest, not the entire
frontend/review tooling; the release-candidate manifest covers those additional files.

Final [container snapshot](../artifacts/stage9/20261107T131512Z-d6ae0b/final-containers.json):
the dedicated review DB is **stopped**, its `opspilot-stage7_stage7-data` volume is
retained, and the original main project containers remain stopped. Docker Desktop
itself is left running; unrelated containers/volumes were not stopped or removed.

Changed runtime/evaluation files are limited to response binding/ambiguity handling
in `evaluations/runners/subjects.py` and snapshot identity display in
`frontend/src/components/dashboard.tsx`. Added `tests/test_stage9_validation.py`,
Stage 9 review/verification scripts, report aggregation and project-scoped evidence
writer, this report, the public evidence summary, new benchmark plans/results and
README/roadmap pointers. Historical report/dataset hash comparison: **all unchanged**.

## 13. Remaining risks and portfolio readiness

- The principal objective remains blocked: no real model/provider/version, genuine
  tool selection, diagnosis, safety behavior, durable handoff or browser run.
- No real calibration or ≥30-case unseen real evaluation; no model superiority,
  API cost/latency, calibrated confidence or autonomous intelligence claim is valid.
- Baseline ambiguity improved on the historical replay but calibration correctness
  fell below the gate. The rule remains limited, not a substitute for semantic
  causal reasoning. The original held-out split is no longer unbiased for tuning.
- Evidence/resource binding and minimum citation checks cannot prove that a model's
  causal explanation is true. Prompt-injection behavior remains model-specific.
- Historical broad connection/recovery/browser timeouts have no established root
  cause. Fresh scoped passes must not be presented as resolving them.
- Inference is not durably resumed; post-handoff action recovery is local,
  transactional and sandbox-specific. No universal external exactly-once promise.
- One job manager, per-process quotas, local bearer identity, privileged local
  operator/DB trust, no off-host audit sealing or public deployment hardening.
- No new full frontend build/browser or connected Linux regression claim. Local
  hardware suitability for the required model/context remains unverified.

The project can demonstrate an implemented tool-mediated investigation architecture
and tested local approval/recovery infrastructure. It **cannot yet be presented as
an independently validated real LLM incident agent**. Stage 9 stops with
**BLOCKED — REAL MODEL UNAVAILABLE**, regardless of deterministic test successes.
No commit, push, cloud resource, deployment or later stage was performed.
