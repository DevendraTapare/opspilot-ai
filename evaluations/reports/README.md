# Evaluation evidence

Reports are local machine-readable experiment evidence, not model input. Diagnostic
JSON stores safe predictions, counters, latency, explicit exclusions, denominators,
intervals and gates. `.plan.json` freezes source/tests/lock/dataset before execution.
PID-suffixed `.traces.jsonl` contains content-free OpenTelemetry spans. Operational
reports include separate synthetic-human trials and actual ledger observations.

New runs require new file names. Failed and partial attempts remain evidence;
neither a fixture smoke nor unavailable B/C case is a real-model benchmark.
Held-out per-case answers remain in controller datasets, not agent contexts.

Actual Stage 5 artifacts and their interpretation are listed in
[STAGE_5_REPORT.md](../../docs/STAGE_5_REPORT.md).

Final evidence: `calibration-final.json`, `development-final.json`,
`held-out-final.json`, `fixture-smoke-final.json`, `operational-final.json`,
`regression-and-operations-final.json`, `release-final.json` and
`stage5-summary.json`. The broad regression retained one failed timing test;
real-model comparisons are unavailable and release readiness is false.
