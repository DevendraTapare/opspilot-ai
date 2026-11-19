# Stage 9A — local model readiness and first-real-run gate

7 November 2026 · `D:\Projects\OpsPilot-AI`

**BLOCKED — No suitable real model is installed; installation/download approval is
required before attempting inference.** No genuine model call, five-case real
investigation or real benchmark was performed. Existing adapters were reused and
inspected, without rebuilding the project. No paid API or stored cloud credential
was used.

## 1. Hardware findings

Read-only checks completed before installation/download decisions: CIM OS/CPU/RAM
and video controllers, filesystem free space, executable/process discovery,
`nvidia-smi`, bounded loopback model-list requests, and model manifest discovery.
Missing commands were checked before invocation. No installer or model was run.

| Requested item | Actual finding |
|---|---|
| Operating system | Windows 11 Home Single Language, 64-bit, version 10.0.22621, build 22621 |
| CPU | AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx |
| Available CPU topology | **1 core / 1 logical processor reported by Windows CIM**; no inference from nominal CPU specifications |
| Physical RAM | 14,903,754,752 bytes, approximately **13.88 GiB** |
| Available RAM | Initial read-only audit: 7,227,724 KiB, **6.89 GiB**; after starting the review DB: 4,989,980 KiB, **4.76 GiB** |
| GPU | NVIDIA GeForce GTX 1650, 4,096 MiB VRAM; AMD Radeon Vega 8 iGPU also present |
| Available NVIDIA memory | `nvidia-smi`: initially **3,935 MiB**, later **3,923 MiB**; compute capability 7.5, driver 610.91 |
| Free disk | Later snapshot: C: 50,664,960,000 bytes (~47.19 GiB); D: 21,966,884,864 bytes (~20.46 GiB) |
| Docker Desktop | Installed and running; Engine 29.9.2 |
| Ollama installed | Not found on PATH or in checked standard per-user/system install locations |
| Ollama running | No Ollama process found; `127.0.0.1:11434/api/tags` unreachable |
| Local models installed | No Ollama model manifests in the configured/default model directory; no reachable Ollama or LM Studio model-list endpoint |

`ollama --version` and `ollama list` could not run because the executable was
absent. This is not a claim to have searched every arbitrary disk directory for
model files. LM Studio and its CLI were also absent from checked paths/PATH.
The iGPU's reported memory is not added to NVIDIA CUDA VRAM. No CPU/BIOS/boot,
driver, WSL or Docker resource settings were changed.

Evidence: [audit snapshot](../artifacts/stage9a/20261107T140438Z-ad6ebb/audit.json).
Its available-RAM snapshot is explicitly after the review DB started; the initial
read-only values are retained separately. The hardware supports an initial small
model trial in principle; successful loading, GPU offload and bounded performance
remain unverified until the runtime/model exists.

## 2. Selected exact model and resource implications

**Candidate: `qwen3:4b-q4_K_M`**, original 4.02B Qwen3, Q4_K_M. The
[official model listing](https://ollama.com/library/qwen3:4b-q4_K_M) advertises tools
and thinking. This is the smaller of the requested 4B/8B candidates, with more
capacity for the existing multi-stage schemas than choosing a sub-2B model solely
for file size. It is a first-test candidate, not a measured quality winner or proof
that every smaller model is unsuitable.

Registry metadata checked without fetching weight blobs:

| Model tag | Current manifest prefix | Model + configuration download bytes |
|---|---|---:|
| Selected `qwen3:4b-q4_K_M` | `2bfd38a7daaf` | **2,620,788,260 (~2.62 GB / 2.44 GiB)** |
| Unqualified `qwen3:4b` | `359d7dd4bcda` | 2,497,293,931 |
| `qwen3:8b` | `500a1f067a9f` | 5,225,388,164 (~5.23 GB) |

The unqualified 4B tag currently refers to a different artifact. Do not silently
substitute it for the reviewed explicit quantization tag. The selected full
manifest identity is:

```text
sha256:2bfd38a7daaf4b1037efe517ccb73d1a3bbd4822cf89f1a82be1569050a114e0
```

The installed digest must be checked again after the approved pull. Tags can change;
the prepared profile refuses a different digest instead of silently changing models.
The API's unprefixed digest and a `sha256:`-prefixed equivalent are both accepted
only when the complete 64-hex identity matches. Registry response bytes, manifest
hashes and layer sizes are retained in the audit. Sources:
[4B registry manifest](https://registry.ollama.ai/v2/library/qwen3/manifests/4b-q4_K_M),
[8B model listing](https://ollama.com/library/qwen3:8b).

The existing native adapter explicitly requests **16,384 context tokens**, temperature
0 and at most 1,600 generated tokens. Changing the server's default context does
not override that per-request `num_ctx`. This stage leaves those settings and the
existing model/tool/time/quality budgets unchanged.

Memory is larger than download size. Using the original
[Qwen3-4B configuration](https://huggingface.co/Qwen/Qwen3-4B/blob/main/config.json),
a conventional uncompressed 16-bit KV cache at 16,384 tokens is approximately:

```text
2 (K,V) × 36 layers × 8 KV heads × 128 head dimension × 16,384 tokens × 2 bytes
= 2.25 GiB
```

Adding ~2.44 GiB quantized weights gives **~4.69 GiB before workspace/runtime
overhead**, exceeding this GPU's free VRAM. This is a planning estimate, not a
measured Ollama allocation; runtime cache formats/placement can differ. Expect
some CPU/RAM offload at the existing context unless the runtime uses a smaller
cache representation. Do not promise GPU-only operation or change cache precision
silently. Budget additional runtime/workspace memory and inspect `ollama ps`,
available RAM and actual latency after loading. One exposed CPU makes offloading
a material latency risk. The 8B weights already exceed all GPU VRAM before cache,
so 8B was not selected for the initial trial.

The driver/compute capability satisfy the published minimums in
[Ollama hardware support](https://docs.ollama.com/gpu) and
[Windows requirements](https://docs.ollama.com/windows). Actual GPU detection still
needs a runtime test. Ollama documents context/offload inspection in
[context length](https://docs.ollama.com/context-length).

## 3. Installation status and exact approval scope

**Not installed; no installer or model weights downloaded.** Ollama release
metadata and Microsoft's winget package metadata identify:

- Runtime candidate **Ollama 0.40.15**, package `Ollama.Ollama`, user scope.
- Windows installer download **1,689,667,936 bytes (~1.69 GB)**.
- Installer SHA-256 `106ef3d2a02437810fba6f574914b1413c512ea84ddd4f184c8e7f434b6f5564`.
- Model download **~2.62 GB**; combined runtime installer/model transfer ~4.31 GB.
- Ollama documents **at least 4 GB installed binary disk space**, in addition to
  model storage. Allow **at least ~6.62 GB steady disk allocation plus installer,
  package cache and temporary space**. Keep ~9–10 GB free across the chosen locations.
  These are disk requirements, not a claim that runtime RAM is 4 GB.

Metadata sources: [official release](https://github.com/ollama/ollama/releases/tag/v0.40.15),
[Microsoft winget manifest](https://github.com/microsoft/winget-pkgs/blob/master/manifests/o/Ollama/Ollama/0.40.15/Ollama.Ollama.installer.yaml),
[retained runtime metadata](../artifacts/stage9a/20261107T140438Z-ad6ebb/runtime-metadata.json).
No signup, cloud resource or credential lookup is required for this local trial.

**Proposed next command, NOT executed:**

```powershell
winget install --id Ollama.Ollama --exact --version 0.40.15 --source winget --scope user --silent
```

Approval must cover installing that runtime and downloading the selected model.
Your Stage 9A instruction explicitly requires approval before model weights, so
execution stops at this boundary. The model's compatibility with actual evidence
is the next experiment, not an already completed integration.

## 4. Provider connection and prepared configuration

`opspilot/agent/providers.py` already has a provider-neutral `DecisionModel`
interface and `HTTPDecisionModel` with:

| Existing path | Status |
|---|---|
| Native local Ollama `/api/chat` | Implemented; not reachable here |
| `openai-compatible` `/chat/completions` | Implemented; local HTTP or authorized hosted HTTPS |
| LM Studio or another compatible local server | Possible through the compatible adapter; no separate provider/plugin required |
| Hosted provider | Requires explicit endpoint/model and authorized credentials; none used |

The process and root dotenv files still have no provider/model/base URL/key
configured. The adapter does not automatically load dotenv configuration or choose
a model. Actual Ollama version, installed-model digest, allocation and connection
smoke results are unavailable; the selected version/tag above are proposals.

Added [Configure-Stage9A-Ollama.ps1](../scripts/Configure-Stage9A-Ollama.ps1), a
process-scoped preparation script. It reads local `/api/tags` and `/api/show`, checks
the exact installed tag/digest, advertised tool capability and ≥16,384-token model
context support, then sets:

```text
OPSPILOT_AGENT_PROVIDER=ollama
OPSPILOT_AGENT_MODEL=qwen3:4b-q4_K_M
OPSPILOT_AGENT_BASE_URL=http://127.0.0.1:11434
```

It removes an inherited provider API key from that process, disables optional remote
LangSmith tracing, and writes no dotenv or user-wide environment settings. It never
installs, pulls, loads or generates with a model. Dot-source it only after approved
installation. It refuses unreachable/missing/changed/unsupported models, rather than
falling back. Mode remains the existing explicit CLI `--mode real`; `--mode fixture`
is separate and performs no inference. No new mode alias or approval bypass exists.

Native Ollama supports [tool calling](https://docs.ollama.com/capabilities/tool-calling)
and [schema outputs](https://docs.ollama.com/capabilities/structured-outputs).
The latter documentation currently excludes Ollama cloud structured outputs, so
do not assume the local profile can simply be redirected to Ollama cloud.
If local resource/latency gates fail, use only an explicitly authorized hosted
HTTPS service with tool calling **and** compatible JSON-schema outputs through the
existing compatible adapter. Such a service needs its own compatibility smoke,
model/version, billing limits and permission; none was contacted here.

## 5. Actual MCP tool-calling smoke result

**NOT RUN — runtime/model absent. Zero real-model calls.** A model metadata badge
or a mocked provider response is not proof of actual model-selected MCP execution.

Code review confirms the implemented path: real planning function call chooses a
typed diagnostic; independent argument/service/incident validation precedes actual
MCP execution; the next model context includes the projected tool observations.
Planning/assessment/root-cause/remediation stages can request further investigation
or abstain. Evidence references, fresh quantitative corroboration and alternatives
are checked; private scenario/fault IDs, seeds and cause-naming log codes are
excluded. The model-facing MCP identity has seven reads and no action/approval
authority. Human authorization and the durable action gateway remain unchanged.

The first post-approval smoke must record model/runtime/digest, incident/run IDs,
actual tool names/arguments, projected responses and references, decision summaries,
latency, safe errors and provider usage. It must demonstrate a model assessment
after receiving the real tool response. Do not publish private chain-of-thought,
keys or privileged controller labels. **Do not launch a larger benchmark unless
this smoke passes.** Thinking defaults, bounded generation/truncation and cold-start
latency remain real-model compatibility risks, not reasons to substitute fixtures.

## 6. Five-case investigation results

All five requested categories are **NOT RUN**, not failed or passed model trials.
Predesignated calibration recipes for the next controlled smoke sequence:

| Category | Existing calibration case | Completed real investigations |
|---|---|---:|
| Straightforward fault | `op5-001` | 0 |
| Dependency failure | `op5-031` | 0 |
| Misleading symptoms/history | `op5-061` | 0 |
| Ambiguous evidence | `op5-055` | 0 |
| Insufficient evidence | `op5-091` | 0 |

The trusted controller may use those IDs to prepare isolated fixtures. The model
must receive only `PublicCase` and positively projected MCP observations, not the
table's category, recipe, expected answer or private fault labels. Preserve every
run including invalid output, timeout, incorrect diagnosis and abstention. No
state-changing remediation is needed to measure diagnosis/proposal quality.

## 7. Benchmark measurements

**Zero real cases attempted/completed**, zero genuine tool selections scored.
Root accuracy, unsupported rate, tool-selection accuracy, appropriate abstention,
remediation-proposal correctness, p50/p95 model-agent latency and cost per
investigation all have **no observed denominator and are unavailable**. No model
tokens or per-case API cost was fabricated. There were no paid calls.

The existing v1 held-out split was inspected and replayed while tuning Stage 9's
baseline. Reusing it must be labeled regression/exploratory evidence, not genuinely
unseen held-out performance. No up-to-30 run was started and no new ground-truth
labels were generated or changed. After a successful real smoke and calibration,
freeze the model/profile/rubric and a properly designated evaluation plan; if no
unexposed existing split is available, disclose that limitation rather than claim
blind evaluation. Keep rules, fixture and real results separate throughout.
The current diagnostic reports also lack a separate persisted proposal-correctness
grade; root accuracy must not be relabeled as remediation accuracy.

## 8. Stage 9 setup-error diagnosis and actual rechecks

Inspected the original Stage 9 JUnit, server sample, fixture and engine code.
Both errors were **connection establishment timeouts before schema creation**:

| Historical node | Failure location/mechanism | Stage 9A outcome |
|---|---|---|
| `test_measured_hard_recovery[postgres-before_approval_restart]` | `tests/conftest.py:98`, initial `admin.begin()`; Psycopg `connect_timeout=3` | Passed unchanged |
| `test_unapproved_actions_fail_closed[postgres-expired]` | Same initial admin connection; no expiry assertion had run | Passed unchanged |

This rules out those particular failures being caused by LLM reasoning, failed
remediation, expiration policy assertions or LangGraph checkpoint deserialization.
The exact low-level reason the PostgreSQL handshake exceeded three seconds is
**not established** by retained diagnostics. Stage 9 server logs show a 192.468s
checkpoint including 74.071s syncing 10,765 files, consistent with possible storage
contention, but not proof of causation. The one exposed logical processor is another
constraint, not a demonstrated causal explanation.

Additional Stage 9A read-only probe: **20/20 fresh connections succeeded**, using
new SQLAlchemy engines and the unchanged three-second timeout, each executing only
`SELECT 1`; mean **92.2ms**, maximum **594ms**. Cumulative
`pg_stat_checkpointer` counters and logs were retained. These were idle-condition
checks, not a reproduction of the original broad-run workload or a reliability SLO.
Evidence: [connection probes](../artifacts/stage9a/20261107T140438Z-ad6ebb/connection-probes.json).

No justified code/DB tuning fix follows from this evidence. Do not increase
timeouts, add hidden test retries, change checkpoint policy or weaken security to
make a pass appear. **The transient environmental root cause remains unresolved.**

Fresh selected recheck, using the existing isolated PG review runner:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_stage9 `
  --node 'tests/test_eval_operations.py::test_measured_hard_recovery[postgres-before_approval_restart]' `
  --node 'tests/test_mcp.py::test_unapproved_actions_fail_closed[postgres-expired]' `
  --node tests/test_agent.py
```

Actual result: **36 passed, 1 skipped, 0 failures/errors**, **38.51s pytest**.
This covers the two affected tests plus existing graph, grounding, no-action,
timeout, scope, provider-failure/no-fallback and mocked HTTP adapter contracts.
The one skip is `test_real_model_smoke_if_explicitly_configured`: **optional external
dependency**, unavailable/unconfigured genuine provider. Mocked HTTP and fixture
tests are explicitly not genuine-model results.

Evidence: [new selected report](../evaluations/reports/stage9-operations-20261107T140222Z-9edccb.json),
[JUnit](../artifacts/stage9/20261107T140222Z-9edccb/pytest.xml),
[per-node evidence](../artifacts/stage9/20261107T140222Z-9edccb/cases.json).
The reused runner creates a new timestamped Stage 9 filename; it does not overwrite
any prior report. Its nine-trial operational aggregate is intentionally incomplete
for this selected run and is not treated as a new full operational gate result.

The original full-suite **301 passed / 49 skipped / 2 setup errors** remains
unchanged. Its 49 skips remain fully classified: **46 expected SQLite/PostgreSQL
environment limitations**, **2 optional running-main-API checks**, **1 optional
real-model check**. The old Docker subset's 48 skips remain 47 missing-PG-URL
variants plus one optional model. See the complete
[Stage 9 skip ledgers](evidence/stage9-validation.json). No unexplained skip is
counted as a pass. **No fresh clean full-suite claim is made.**

Prepared profile checks: PowerShell AST parsing passed; **7/7 mocked metadata
contracts passed** (both digest representations, changed digest, absent model,
missing tools, inadequate context, unreachable service). These checks made no
network, MCP or model calls. [Contract evidence](../artifacts/stage9a/20261107T140438Z-ad6ebb/profile-contracts.json).
Python Ruff lint and formatting checks passed (153 files); the candidate-file
secret scan passed with **232 files, zero findings**. These checks do not make
the historical broad suite clean. The complete verification/integrity/shutdown
record is [verification.json](../artifacts/stage9a/20261107T140438Z-ad6ebb/verification.json).

## 9. Files changed and preserved state

Added public source/documents:

- `scripts/Configure-Stage9A-Ollama.ps1` — guarded process-local configuration only.
- `docs/STAGE_9A_REAL_MODEL_UNBLOCK.md` — this report and the approval-ready commands.

Added private audit/probe/metadata/configuration-contract records under
`artifacts/stage9a/20261107T140438Z-ad6ebb/`, plus the new selected test report,
JUnit/log/ledger paths listed above. Runtime/provider/graph/MCP/approval/checkpoint
code, dependency locks, labels and historical research reports were not changed.
Protected hashes were captured before preparation and checked again at completion.

Only the dedicated Stage 7 review DB was started for verification; its retained
volume and all main/historical simulator databases were preserved. Final shutdown
and integrity/secret-scan results are recorded with the audit evidence. No model
weights, test credentials or private logs are added to publishable files.

## 10. Approval-ready commands and remaining limitations

**The following installation/download commands are proposals. They were NOT run.**
Run only after approving the specified runtime and model. The Windows installer
normally starts a tray server; quit that newly installed instance before launching
the controlled server below. Do not replace an unrelated existing listener.

```powershell
Set-Location D:\Projects\OpsPilot-AI
$ErrorActionPreference = 'Stop'
winget install --id Ollama.Ollama --exact --version 0.40.15 --source winget --scope user --silent

# After approving installation and quitting any newly auto-started tray instance:
$opspilotOllama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$opspilotModelStore = Join-Path (Get-Location) 'artifacts\ollama-models'
New-Item -ItemType Directory -Path $opspilotModelStore -Force | Out-Null
$env:OLLAMA_MODELS = $opspilotModelStore
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NO_CLOUD = '1'
if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 11434 is occupied; preserve the existing process and inspect it first.'
}
$opspilotServer = Start-Process -FilePath $opspilotOllama -ArgumentList 'serve' -WindowStyle Hidden -PassThru

# Wait for the loopback API, then the separately approved model download:
$opspilotReady = $false
for ($opspilotAttempt = 0; $opspilotAttempt -lt 20; $opspilotAttempt++) {
    if ($opspilotServer.HasExited) { throw 'Owned Ollama server exited; inspect startup.' }
    try {
        $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 1
        $opspilotReady = $true
        break
    } catch { Start-Sleep -Milliseconds 250 }
}
if (-not $opspilotReady) { throw 'Ollama readiness deadline exceeded; no model pull attempted.' }
& $opspilotOllama pull 'qwen3:4b-q4_K_M'
if ($LASTEXITCODE -ne 0) { throw 'Model pull failed; do not start inference.' }
. .\scripts\Configure-Stage9A-Ollama.ps1
& $opspilotOllama --version
& $opspilotOllama list

# After the first controlled inference, verify actual allocation/context:
& $opspilotOllama ps
```

The profile targets native Windows Python verification. No API key is required;
the model's `artifacts` directory is ignored by Git and Docker build context.
The server environment applies to the explicitly started process; it does not
reconfigure an already running tray instance. Stop only the process handle created
above when finished: `Stop-Process -Id $opspilotServer.Id` after confirming that it
is still that Ollama process. Do not kill all Ollama or Docker processes.

Outstanding: successful model loading/offload; native function-call and structured
output behavior under current budgets; measured diagnosis/proposal/abstention
quality; thinking-token/truncation behavior; model-driven safety and durable handoff;
five real investigations; and any up-to-30 benchmark. Original transient database
timeouts and held-out contamination remain independent limits. No automatic
remediation or public deployment is authorized by installing a model.

## 11. Final verdict

**BLOCKED — No suitable installed real model; first real integration cannot run.**
Hardware/model/provider inspection, a concrete local candidate/configuration and
the requested affected-test rechecks are complete. Real MCP/model smoke and larger
evaluation remain gated. Please approve **Ollama 0.40.15 installation (~1.69 GB
installer, ≥4 GB installed binaries) plus `qwen3:4b-q4_K_M` (~2.62 GB model)** before
any download/install. Existing available disk supports the proposed storage budget;
runtime memory/performance remains subject to the first smoke, not a guarantee.

No historical reports/labels changed, secrets disclosed, model installed, paid API
used, Git commit/push, cloud resource or deployment. Stop at Stage 9A approval.
