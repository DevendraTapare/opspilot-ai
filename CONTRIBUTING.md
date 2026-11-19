# Contributing and reproducible checks

Use Python 3.12, Node 24 LTS, uv 0.11.23 and Docker Linux containers. Install with
`uv sync --locked` and `npm ci --ignore-scripts` in frontend. Private initialization
is local only; `.env.example` is a placeholder contract. Never add generated
credentials, logs, DB/checkpoint data, model weights or environment files to Git.

The README lists local checks. `scripts.review_stage7` uses its separately labeled
review DB and fresh per-test schemas; it rejects any other container identity.
`scripts.verify_release_browser` uses fresh synthetic credentials and preserves
new screenshots/reports. `scripts.docker_release_smoke` builds a separate Compose
project and retains its volume. Run browser checks after DB-restart tests, not
concurrently against the same review DB. Stop only owned project services.

CI defines independent dependency/hygiene, PostgreSQL/MCP/security and Chromium
jobs. Permissions are read-only, actions are SHA-pinned, and no cloud/provider
secret is required. Failures propagate; no continue-on-error or retry hides a
failed gate. GitHub execution is unverified until an owner actually publishes the
repository and runs the workflow. No publication is part of this preparation.

Biome applies four explicit frontend safety rules (eval, unsafe HTML, debugger,
duplicate JSX props); TypeScript performs strict type checks. This is not a claim
of a complete style/accessibility lint policy. Ruff checks Python lint/format.
pip-audit and npm audit query known advisories; neither proves package provenance.

Keep evaluation splits/frozen manifests and historical reports intact. Never give
answer keys to the investigator or silently convert a real-provider failure into
a fixture result. Publish denominators, exclusions, failed gates and model identity.
Public test fixtures are synthetic inputs with no production authority; generated
runtime credentials and private test logs are excluded. Do not reuse fixture
identities in an exposed service. No open-source license has been selected yet.
