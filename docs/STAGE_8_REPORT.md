# Stage 8 — portfolio release preparation

**Verdict: CONDITIONAL GitHub portfolio preview. Public deployment: NOT READY.**
Prepared November 4, 2026 in `D:\Projects\OpsPilot-AI`. No Git initialization,
commit, push, cloud resource, image publication or deployment was performed.
There is no configured/evaluated real model. No Stage 9 work was started.

## 1. Completion by stage

These labels retain each stage's recorded verification scope; later passing
rechecks do not rewrite historical failed runs.

| Stage | Implemented scope | Recorded disposition |
|---|---|---|
| 1 | Seeded simulator, incident API, persistence, real Docker/PostgreSQL checks | PASS |
| 2 | Real MCP protocol, scoped tools, separate authorization gateway | PASS for local scope |
| 3 | Typed conditional LangGraph investigation, provider adapters and fixture separation | CONDITIONAL: no real model; historical transport timeout |
| 4 | Human approval, PostgreSQL checkpoints, idempotency, crash recovery, verification | Scoped checks PASS; overall CONDITIONAL inherited limits |
| 5 | 120-recipe evaluation, explicit denominators, OTel, release gates | CONDITIONAL: real models unavailable; baseline unsupported gate FAIL |
| 6 | Six-view Next dashboard, backend authorization, Chromium lifecycle | CONDITIONAL: real model unavailable; broad timing failures retained |
| 7 | Adversarial review, four confirmed fixes, restart/replay/security evidence | CONDITIONAL: no real-model resistance; recovery timeout retained |
| 8 | Release assets, screenshots, CI preparation, hygiene, quality checks and hosting plan | CONDITIONAL preview; no public deployment |

Original [Stage 1](STAGE_1_REPORT.md), [2](STAGE_2_REPORT.md), [3](STAGE_3_REPORT.md),
[4](STAGE_4_REPORT.md), [5](STAGE_5_REPORT.md), [6](STAGE_6_REPORT.md) and
[7](STAGE_7_REPORT.md) reports remain unchanged.

## 2. Release assets and actual changes

- Rewrote README around business value, actual agent decisions, architecture,
  technology/setup, qualified metrics, security, limitations and demonstration.
- Added state-machine, threat-model, deployment, recording, resume and release
  checklist documents, plus CONTRIBUTING.md and SECURITY.md.
- Captured/reviewed seven real Chromium screenshots with source hashes. No mockup,
  AI-generated screenshot, real-model recording or hosted video was fabricated.
- Exported positive aggregate benchmark/release evidence to `docs/evidence/`.
  Historical evaluation originals/raw private evidence remain on disk.
- Prepared three SHA-pinned, read-only GitHub Actions jobs and dependency-update
  configuration. Local YAML/security assertions passed; GitHub execution is unverified.
- Added publication scanning, isolated browser verification, Docker startup smoke
  and evidence export scripts. The release browser harness uses fresh runtime
  credentials and unique output directories, preserving Stage 6 evidence.
- Expanded ignore policies for private environments, credentials, logs, volumes,
  checkpoints, caches, dumps and model weights. Public fixture builders have no
  production authority; generated runtime credentials are never release assets.
- Repaired the Docker **test** target to include accumulated scripts, review and
  evaluation support and an artifact directory. The runtime image still contains
  neither evaluation datasets nor operator/test scripts or private environment files.
- Added pinned Biome 2.6.4 and four explicit frontend safety rules. Existing strict
  TypeScript checking remains separate; this is not a complete accessibility/style audit.
- Fixed an evaluation-view defect found during screenshot review: baseline gates
  were read from a report containing only real-model arms. The view now uses the
  selected split's recorded `gates.baseline`. Chromium asserts the unsupported
  diagnosis **FAIL** is visible; the final screenshot shows the actual gate list.
- Replaced four synthetic static test canaries flagged by the publication heuristic
  with runtime-generated values. Six affected regressions passed; control assertions
  and application authentication/approval/time limits were unchanged.

Full inventory: [FILE_MANIFEST.md](FILE_MANIFEST.md).

## 3. Actual quality results

Host: Windows 11, Python 3.12.3, Node 24.14.1/npm 11.11.0; Docker Linux containers,
pinned PostgreSQL 18.6. Backend uv lock remains 80 packages. Frontend lock adds only
the pinned lint tool and platform dependencies. No runtime dependency upgrade or
schema migration was required; schema remains `0004_dashboard`.

| Check | Actual result |
|---|---|
| Broad existing Python/API/MCP/PG/durable/security regression | **286 passed, 49 skipped, 1 setup error**, 713.90s |
| Exact unchanged failing-case recheck | **1 passed**, 7.83s |
| New release-hygiene checks | **12 passed**, 0.19s |
| Affected runtime-canary regression | **6 passed** |
| Linux Docker test-target sample | **93 passed, 48 skipped**, 88.26s; one retained warning |
| Initial combined Chromium run | **4 passed, 2 failed**, 147.757s |
| Second combined Chromium run | **4 passed, 2 failed**, 123.692s |
| Separate rejection / timeout Chromium rechecks | **1 passed each**, 51.827s / 45.913s |
| Final post-fix production-build Chromium run | **6 passed, 0 failed/skipped/flaky**, **72.204s** |
| Python lint / format; uv lock consistency | Passed |
| Frontend Biome / strict TypeScript / production build | Passed after final UI fix |
| Python dependency audit | pip-audit 2.10.1: **78 packages**, zero known advisories, zero unchecked packages |
| npm dependency audit | **162 dependencies**, zero reported advisories at all severities |
| Publication source scan | Passed: 207 candidate files, zero findings; not a Git index/history certification |
| Browser secret / release-document links | Ten JavaScript files: zero configured-secret matches; 62 local links: zero missing |
| Docker runtime startup | Passed: readiness 200, three services, three healthy workloads, anonymous fault injection 401 |
| Runtime image boundary | Passed: non-root UID 10001; private config, datasets and operator scripts absent |
| CI definition | Local YAML parse, read-only permission/action-SHA assertions passed; remote execution unavailable |

The broad error was
`test_direct_fault_does_not_modify_other_fixtures[postgres-payment-service-worker-saturation]`:
PostgreSQL connection setup timed out. Its assertion did not execute in that run;
the exact case passed unchanged in isolation. The latest result for the original
336 test nodes is 287 passed/49 skipped, **not a second clean full-suite run**.
The twelve new guard tests are separate and are not pooled into that full-run count.
The 49 skips are 46 SQLite variants requiring PostgreSQL semantics, two unconfigured
opt-in main-API tests and one unconfigured real-model smoke. Real isolated HTTP,
MCP/PostgreSQL integrations and controlled database/process restart tests did run.

Initial browser failures were backend/login timeouts. The second run completed the
entire approved lifecycle but timed out on rejection/timeout test logins. Separate
rechecks and the final unchanged limits passed; their causes are not established
or declared permanently fixed. No authorization, quota, time budget or expected
outcome was relaxed. The final gate-rendering assertion is stronger than before.

Early tooling failures are retained too: the first nine-case guard attempt had
seven passes/two setup errors because its temporary parent directory was absent;
the first Docker smoke accessed a nonexistent singular `metric` response field.
The parent directory and harness's plural `metrics` access were corrected. These
were verification-harness issues, not claimed application vulnerabilities.
The first publication scan flagged four synthetic canaries, not exposed live secrets.

## 4. Evidence and reproducibility

Public positive export: [release-stage8.json](evidence/release-stage8.json).
It records separate runs, source digests, audit denominators and blocked gates.
It contains no raw diagnostic/log content or human credentials. Screenshot
provenance is [here](screenshots/provenance.json).

Local raw evidence, deliberately excluded from publication:

- Full regression: `artifacts/stage7/20261104T112126Z-8038c0/`.
- Unchanged setup-error recheck: `artifacts/stage7/20261104T113746Z-14efe6/`.
- Canary recheck: `artifacts/stage7/20261104T114156Z-5ac79d/`.
- Final browser: `artifacts/stage8/20261104T115404Z-browser-78c060/`;
  two earlier combined and two isolated runs remain in their own Stage 8 folders.
- Docker startup: `artifacts/stage8/20261104T113744Z-docker-b0e41e/result.json`;
  earlier harness failure remains separate. Portable sample: `artifacts/stage8/docker-portable/`.
- Private audits/builds/checks: `artifacts/stage8-*` and `artifacts/stage8/`.

Use the README and contributor commands. `scripts.review_stage7` intentionally
reuses the independently labeled review infrastructure and writes a fresh evidence
folder; it does not rewrite the historical Stage 7 report. Browser tests run after
the database restart suite. Only named review/release-check services are stopped;
their data volumes and all historical reports are retained. Main stack/data were
not started, reset or remediated.

## 5. Real-model evaluation and benchmark claims

Real model: **unconfigured/unavailable**, zero attempted real-model benchmark cases.
No real-model accuracy, cost, token count, latency, superiority or prompt-injection
resistance is claimed. Provider errors never become hidden fixture results.

The historical Stage 5 suite has 120 recipes/20 families, split 20/60/40. Held-out
rules results: root accuracy **24/26 (92.31%)**, task completion **36/40 (90%)**,
unsupported diagnoses **2/28 (7.14%, failed ≤5% gate)**, p50/p95 diagnostic latency
**968/1,719ms**, 200 calls/40 incidents, twelve abstentions and zero timeouts.
Real arms B/C each exclude 120 cases across all splits; neither attempted inference.
These frozen-source results are not a fresh benchmark of this release.

Separate historical operational evidence: three hard-process recoveries out of
three, zero extra effects in four replay/recovery trials, six correct verification
judgments out of six. Small related simulator samples do not establish production
SLOs. Denominators/intervals/gates: [benchmark export](evidence/benchmark-stage5.json)
and [methodology](EVALUATION_METHODOLOGY.md). Release gates remain blocked.

## 6. Security and demo readiness

Stage 7's fourteen security and eleven reliability review groups remain covered
by the current regression, including real MCP, role constraints, replay/target
substitution, process/database restart and uncertain-acknowledgment reconciliation.
Four previously confirmed security findings remain fixed. No model-level adversarial
result is inferred from deterministic tests.

The final browser verified healthy services → controlled checkout incident → fixture
investigation → five real MCP calls → exact backend human approval → one sandbox
action → measured recovery → audit. It also verified rejection, a timed-out run
with no approval, responsive views and actual backend outage/recovery. Humans in
automation are explicitly synthetic. [Seven reviewed screenshots](screenshots/README.md)
and the [five-minute recording script](DEMO_SCRIPT.md) are ready. No video was recorded
or uploaded. A genuine LLM demonstration remains unavailable.

## 7. Deployment and unresolved limits

Recommendation: local/video portfolio first; later, a private invited-user trial
on one small VM with Next, private FastAPI/LangGraph/MCP/authorizer, isolated
simulator and private PostgreSQL. Budget **US$25–60/month is an estimate**, excluding
inference/tax/domain, not a price quote. [Hosting plan and primary references](DEPLOYMENT_ARCHITECTURE.md).

Public hosting requires whole-surface TLS authentication/MFA, shared quotas and
spend ceilings, sandbox CPU/RAM/egress isolation, restricted roles/secrets,
backup/restore tests, retention/off-host audits, production load/failure testing
and passing real-model gates. Current loopback checks do not support an arbitrary
split-host topology. No privileged API may be anonymous.

Remaining limits include unverified real-model behavior; failed baseline gate;
intermittent broad-run connection/recovery/browser timeouts; one job manager;
non-resumable investigation inference; per-process quotas; trusted local OS/DB owners;
SDK transport exception groups; missing remote identity/retention/off-host audit
sealing; and exactly-once guarantees restricted to transactional simulator effects.
Application advisory scans are not container OS, model provenance or general DLP
audits. Pattern scans do not certify images or future Git history. A license and
the eventual staged diff need owner review before public/open-source claims.

## 8. GitHub verdict and resume highlights

**CONDITIONAL PREVIEW:** source, documentation, measured evidence, screenshots and
CI definitions are prepared. This workspace has no Git repository/index to certify;
candidate-file scans and later tracked-file scans are distinct. GitHub CI has not
run, and there is no hosted release. Public deployment and a performance claim
for a real LLM are blocked. No badge implies otherwise.

Suggested measured ATS bullets:

- Built a three-service FastAPI/PostgreSQL incident lab with a typed LangGraph
  investigator, seven real MCP diagnostic tools and a Next.js operations console.
- Implemented exact-action human approval for three sandbox tools, PostgreSQL
  checkpoints, transactional idempotency and reconciliation; tested crash/replay
  boundaries and measured post-action verification.
- Created a 120-recipe benchmark with explicit denominators; the historical rules
  baseline completed 36/40 held-out tasks while exposing a failed 7.14% unsupported
  diagnosis gate and unavailable real-model comparisons.

[Additional qualified bullets and claims to avoid](RESUME_HIGHLIGHTS.md).
Stop after release preparation. No commit, push, cloud creation or deployment.
