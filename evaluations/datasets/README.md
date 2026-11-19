# Benchmark datasets

`v1/manifest.json` pins 120 controller recipes and file checksums: calibration 20,
development 60, final held-out 40. These files contain private setup and expected
answers; never pass them to an agent or provider. Subjects receive `PublicCase`
and positively projected operational MCP evidence only.

The generator is `python -m evaluations.runners.dataset`. Existing versioned data
must not be regenerated to fit held-out results. Change the dataset version for a
new benchmark. Tests check structural recipe uniqueness excluding seeds and labels.
There are twenty families, not 120 independent underlying fault mechanisms.

See [methodology](../../docs/EVALUATION_METHODOLOGY.md) for category coverage,
operational contingencies, scoring policies, isolation and limitations.
