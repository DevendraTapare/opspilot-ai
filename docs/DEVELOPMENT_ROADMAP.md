# Development roadmap

## Stage 1 — current scope

Foundation, protected control APIs, isolated deterministic service models,
observable faults, real PostgreSQL persistence, migrations, metrics, safe logs,
incident detection/recovery, Docker Compose, tests, and reproducible documentation.
The verification report records the exact scope that was actually executed.

## Stage 2 — current implementation

Real MCP discovery and typed observations, caller/service scopes, a separate action
authorization service, interactive operator approval, signed one-use grants,
persisted action audits, and protocol/security tests. See STAGE_2_REPORT.md.
Stage 2 remains the authorization boundary for simulator actions.

## Stage 3 — current implementation

Typed LangGraph state, bounded read-only MCP investigations, conditional evidence
loops, provider-neutral structured model decisions, real HTTP provider adapters,
explicit deterministic test fixtures, citation checks, abstention, and recommendations
for human review. See STAGE_3_REPORT.md for actual verification and model availability.
No automatic remediation is implemented.

## Later possibilities — require separate scope

- Longer-running discrete event scheduling with queues shared across bursts.
- Richer dependency topologies and causal traces.
- Durable retention policies, metric downsampling, and export adapters.
- Agent action audits, policy checks, and repeatable recovery evaluations.
- Optional UI after the backend and agent contracts are stable.
- Multi-user authorization and TLS if the project ever moves beyond local use.

## Stage 4 — current implementation

Persistent PostgreSQL execution checkpoints, stable run/thread IDs, authenticated
interactive human approval and revocation, immutable action fingerprints,
concurrent resume exclusion, backend transactional idempotency, reconciliation,
one-time measured verification, separately approved recovery and crash tests.
The Stage 3 model still has only read-only tools. See STAGE_4_REPORT.md.

## Stage 5 — current implementation

Versioned calibration/development/held-out recipes, explicit metrics and uncertainty,
real MCP-backed rules/LLM/structured-agent comparison runners, synthetic-human
operational probes, local OpenTelemetry traces and fail-closed release reports.
See STAGE_5_REPORT.md for actual results, sample sizes and unavailable real models.

## Stage 6 — current implementation

Local Next.js dashboard, six operations views, actual evidence, authenticated
human decisions, explicit durable resume and historical evaluation visibility.
See STAGE_6_REPORT.md for actual Chromium verification and model availability.

## Stage 7 — current implementation

Isolated adversarial and failure-injection review, OWASP Agentic risk mapping,
per-test evidence ledgers, response resource binding, human-session rotation,
absolute body deadlines and persisted cited-fact attestation. Actual outcomes
and unresolved real-model limits are in STAGE_7_REPORT.md. Historical reports
remain unchanged.

## Stage 8 — portfolio release preparation

Polished README, actual browser captures, five-minute recording script, source and
credential hygiene checks, reviewed historical benchmark aggregates, SHA-pinned CI,
state-machine/threat/deployment documents and measured resume highlights. Real-model
evidence and public-deployment prerequisites remain blocked. See STAGE_8_REPORT.md.

## Stage 9 — real-model validation review

Capability audit, configuration/hardware checks, historical unsupported-diagnosis
investigation, benchmark response binding and conservative ambiguity handling,
preserved before/after deterministic replays and PostgreSQL/security recovery
regressions. Genuine-model validation is blocked by absent runtime/model/provider
configuration. See [STAGE_9_REAL_LLM_VALIDATION.md](STAGE_9_REAL_LLM_VALIDATION.md)
for actual results, the calibration gate failure and all unresolved risks.

Stop after Stage 9 verification. No commit, push, resources or deployment.
