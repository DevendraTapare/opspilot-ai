# Public evidence index

This directory contains reviewed aggregate facts, not private diagnostic logs,
checkpoint state or approval credentials.

- `benchmark-stage5.json`: positive export of historical held-out metric
  denominators/intervals, gates, separate operational aggregates and source hashes.
  No per-case fault answer or raw model/log payload is included. It is not a
  rerun of the current release. Original `evaluations/reports/*.json` records and
  dataset manifests remain preserved.
- `release-stage8.json`: current preparation check summaries and evidence digests,
  including failed attempts and reruns. Counts are not pooled as independent trials.
- `../screenshots/provenance.json`: actual Chromium capture provenance and hashes;
  fixture mode and synthetic test human are explicit.

Historical Stage 1–7 documents retain their original links to local ignored
`artifacts/` evidence. Those raw files are deliberately not public repository
assets. They remain on this workspace; a reader can reproduce checks locally.
An unavailable private raw link is not presented as hosted evidence. New README
claims link to public aggregates and source assertions instead.

Never update a frozen benchmark file with a new source revision. Create a new
versioned experiment, keep its model/mode and exclusions explicit, and preserve
failed release gates. Real-model sample size remains zero.
