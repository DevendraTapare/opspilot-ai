# Portfolio release checklist

This is a **conditional portfolio preview**, not a production or real-model release.
See [Stage 8 measured results](STAGE_8_REPORT.md) before publishing any claim.

| Area | Preparation / remaining requirement |
|---|---|
| Overview | README covers business problem, agent decisions, architecture, setup, measured metrics and limits |
| Technical docs | Agent, state machines, MCP, human approval, durability, evaluation, threat model and hosting plan |
| Demo | Five-minute recording script; real browser screenshots; no recorded/uploaded video yet |
| Model evidence | Real-provider adapters exist; real-model evaluations and adversarial behavior **unavailable** |
| Benchmarks | Preserve historical reports; identify deterministic baseline and failed unsupported-diagnosis gate |
| Quality | Actual commands/results and retained failed attempts in Stage 8 report; do not call reruns a clean full run |
| CI | SHA-pinned Actions, read-only permissions, isolated DB and browser jobs; GitHub execution still unverified |
| Dependencies | Locked runtime/frontend dependencies; pip-audit/npm advisory checks; no claim of full supply-chain audit |
| Publication | Candidate/tracked-source scan, reviewed screenshots, private artifact exclusions; no commit/push performed |
| License | Owner must choose licensing policy before describing this as open source; no license invented |
| Deployment | Public authentication/quotas/isolation/identity and gate requirements remain; no resources created |

## Before a later owner-controlled publication

Review `git status` and the exact staged diff after creating/selecting the intended
repository. Do not stage with an unreviewed blanket command. Re-run
`python -m scripts.release_hygiene --output artifacts/stage8/prepublish.json`;
when a repository exists, it scans tracked files, including files already tracked
despite `.gitignore`. Review newly staged files again: an untracked-file candidate
scan is not proof about the final Git index/history. Run the workflow on the actual
remote before claiming CI passes. Enable private vulnerability reporting if desired.

Publish source, versioned datasets and historical aggregate evaluation JSON, not
environment files, generated test credentials, raw traces/logs, checkpoints,
DB volumes, local caches or weights. Historical raw evidence stays on disk;
[reviewed aggregate exports](evidence/README.md) make key claims reviewable in GitHub.
Held-out data is controller-only at runtime; public repository access means it is
not a secret from a human reader, and it must never be mounted/given to the agent.

## Public deployment gate

The public deployment verdict is **NOT READY**. Local authentication and the
independent approval policy do not provide a remote identity service or a shared
quota store. Follow [deployment prerequisites](DEPLOYMENT_ARCHITECTURE.md), resolve
or characterize intermittent failures, and obtain actual real-model evidence.
No CI workflow creates resources, publishes images or deploys this project.
