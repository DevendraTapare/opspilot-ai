# Resume-ready technical highlights

Use the facts and qualifications together. Historical metrics are Stage 5 results,
not measurements of a real LLM or the current release. Current release test counts
belong in STAGE_8_REPORT.md. No production users, revenue or MTTR impact was measured.

- Built an incident-response lab with FastAPI, PostgreSQL and a Next.js dashboard,
  simulating three dependent services and five injected fault mechanisms with
  deterministic, resettable workloads and persisted logs/metrics.
- Implemented a typed LangGraph investigator and official MCP SDK integration with
  seven read-only diagnostic tools, conditional hypothesis/evidence loops, budgets,
  structured outputs and abstention; real-provider adapters are implemented but
  real-model diagnostic performance remains unverified.
- Engineered exact-action human approval for three reversible sandbox tools,
  including run/target/argument fingerprinting, expiration/revocation, independent
  authorization and PostgreSQL-checkpointed execution with durable idempotency and
  reconciliation after uncertain acknowledgments.
- Created a 120-recipe evaluation suite across 20 families and three splits; the
  historical deterministic baseline completed 36/40 held-out tasks and identified
  24/26 answerable root causes, while exposing a failed 7.14% unsupported-diagnosis
  gate and unavailable real-model comparisons.
- Conducted an adversarial review across 25 security/reliability groups and fixed
  four confirmed issues in evidence binding/integrity, credential rotation and
  request-body deadlines; exercised real MCP, PostgreSQL role constraints and
  crash/replay tests without claiming general prompt-injection immunity.
- Instrumented incident, model, MCP, approval, action and verification paths with
  content-sanitized OpenTelemetry spans and structured JSON evidence; separated
  model inference, fixture testing and operational safety measurements.

## ATS skills supported by source

Python, FastAPI, Pydantic v2, LangGraph, Model Context Protocol (MCP), tool calling,
structured output validation, human-in-the-loop approval, PostgreSQL, SQLAlchemy,
Alembic, checkpointing, idempotency, reconciliation, least privilege, prompt injection
testing, OpenTelemetry, evaluation datasets, release gates, Docker Compose, Pytest,
Next.js, React, TypeScript, Tailwind CSS, Playwright, GitHub Actions preparation.

## Claims to avoid

“Autonomous production remediation,” “LLM accuracy 92%,” “100% secure,”
“zero failures,” “exactly once for any external action,” “deployed to cloud,”
“reduced MTTR by X%,” “outperformed other agents,” and “CI is green on GitHub.”
No evidence supports those statements. A real-model demo and measurements are
the highest-value remaining portfolio improvement; do not fill that gap with fixtures.
