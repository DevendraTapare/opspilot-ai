# Five-minute recording script

The current recording is an **integration demonstration with deterministic fixture
decisions**, real MCP, PostgreSQL and browser behavior. Do not call it genuine LLM
reasoning. A real-AI recording requires an explicitly configured and verified model;
show its name, mode and measured usage without revealing credentials.

## Preparation, off camera

Use the README/`frontend/README.md` Windows startup and shutdown commands. Keep all
services on loopback. Use a dedicated local demo database if preserving existing
fixtures matters; never point test/reset scripts at another project or production.
Stage 8 automated verification uses a fresh UUID schema in the separate review DB,
fresh test credentials and an explicitly labeled synthetic test human.

For a human recording, sign in privately with the operator credential. Deliberately
enable only local sandbox actions as documented in the frontend guide, recreate
the authorizer and restart the dashboard. Do not record tokens, environment files,
password manager screens, login input, terminal environment dumps or private logs.
Restore disabled actions afterward. Never edit approval rows or bypass a failure.

Create actual healthy workload measurements for all three fictional services before
the take; a label without a metric is not a healthy baseline. Use the authenticated
simulator workload APIs from `docs/API.md`. Reset only fixtures explicitly selected
for the take; reset retains history. Use checkout `worker-saturation`, which is
supported by the fixture investigator. Keep optional continuous traffic stopped.

## Timed shot list and narration

| Time | On screen / action | Narration |
|---|---|---|
| 0:00–0:30 | Overview: three healthy metric windows; backend connected | “OpsPilot is a reproducible incident-response sandbox. These measurements come from real simulated requests. This take uses deterministic fixture decisions; no LLM inference occurs.” |
| 0:30–1:00 | Simulate incident, checkout worker saturation; confirm selected-fixture reset | “The fault occupies modeled workers and changes observed errors/utilization. It is not only a status label. No production system is involved.” |
| 1:00–1:35 | Launch investigation; show mode and budget, then workspace | “In real mode a configured model chooses diagnostics and compares hypotheses. This fixture validates the same graph, tools and enforcement without pretending to reason.” |
| 1:35–2:15 | Inspect get_incident, metrics, logs, dependencies and deployments | “These are actual MCP calls with bounded results. The agent receives operational evidence, not the fixture answer. Dependencies and competing explanations are checked.” |
| 2:15–2:50 | Cited root-cause proposal, uncertainty and remediation plan | “The worker-saturation proposal cites measurements. A recommendation grants no authority. Missing evidence or invalid decisions must abstain or fail visibly.” |
| 2:50–3:35 | Approval center: exact tool/target/arguments, evidence, risk, expiry, full fingerprint; approve | “A separately authenticated human approves this exact action for this run. Changing the target or arguments invalidates authority; a model cannot approve itself.” |
| 3:35–4:15 | Explicitly execute approved action; wait for verification | “Approval and execution are separate. The gateway commits the sandbox effect and ledger atomically. Retries reconcile that record rather than repeating the effect.” |
| 4:15–4:45 | Verified metric window and final audit timeline | “The action result and recovery are different facts. Verification measures health, latency and error rate. A failed check needs a new authorized recovery intent.” |
| 4:45–5:00 | Evaluations: rules metrics, unavailable model arms and failed gates | “The 40-case held-out rules sample completed 36 tasks. Real-model attempts are zero, and the unsupported-diagnosis gate fails. Those limits remain visible.” |

## If the take fails

Show the actual error and stop the take. Do not manufacture success, edit a DB row,
reuse an expired approval or hide a failed health check. Record a new run after
diagnosing the issue; independently approve any new exact action. Preserve the
failed run/audit. If a provider is unavailable, either stop the real-model recording
or explicitly begin a separate fixture demonstration. Do not splice fixture output
into a real-model claim. Do not announce recovery before `verified` is persisted.

## Deliverables

Record 1080p at readable zoom, hide browser personal information, retain the fixture
notice and captions, and use the final 15 seconds for limitations. The repository
contains an actual Chromium screenshot set and this recording script, **not a
recorded or uploaded video**. No video link or public endpoint is fabricated.
