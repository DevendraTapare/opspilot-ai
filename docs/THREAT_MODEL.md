# Threat model

Scope: a fictional local simulator, trusted host, one investigator and dashboard
job manager, independent human authority and PostgreSQL. [The OWASP Agentic review](SECURITY_REVIEW.md)
contains individual tests and risk mapping. No penetration-test certification is claimed.

| Asset / boundary | Trusted component | Untrusted input |
|---|---|---|
| Diagnostic integrity | Typed gateway, persisted simulator facts, projections | Logs, tool content, provider outputs |
| Human authority | Separate operator policy and exact approved intent | Model statements, tool approval flags, resume data |
| Action identity | Run/incident/target/arguments fingerprint and ledger | Replayed grants, changed arguments, concurrent delivery |
| Session | Private operator registry and credential-bound HMAC | Cookies, browser input, cross-origin requests |
| Durable history | DB privileges and immutable authority/audit triggers | Worker/operator UPDATE/DELETE attempts |
| Credentials | Private files and restricted server processes | Browser bundles, errors, traces, repository publication |
| Resources | Body/result limits, deadlines, graph/caller quotas | Oversized/drip-fed requests, excessive calls |

The model receives no DB, signing, human, simulator-control, shell, unrestricted
file or SQL capability. Next proxies only fixed paths to a loopback backend and
keeps its key server-side. Local read views cover all three services; they are not
a multi-tenant read authorization system.

## Attack controls

- Injection and goal hijack: positive projections, untrusted-data markings,
  structured output validation, fixed tool registry and budgets. Persisted test log
  payloads are excluded from context; other allowed text can still carry instructions.
  Real-model persuasion resistance is unverified.
- Evidence forgery: bind tool responses to requested resources/topology and compare
  cited projected facts with persisted telemetry at handoff. IDs alone do not
  authenticate values. Completeness and causal reasoning remain separate concerns.
- Confused authority: independently check identity/scope, exact fingerprint,
  current grant state and preconditions. Reject target substitution, replay,
  cross-run authority, expiry and revocation. Credential rotation invalidates sessions.
- Duplicate effects: atomic effect/grant/ledger transaction, unique action identity
  and reconciliation before redelivery. No general remote-side-effect guarantee.
- Audit tampering: tested restricted roles and triggers deny edits; the DB owner
  can change the schema or bypass those protections.
- Denial of service: bounded JSON/results, absolute body deadlines, quotas and
  graph budgets. Slow headers, volumetric traffic and many concurrent sockets have
  not been stress-tested.
- Publication: ignore private environments, raw logs, checkpoints, volumes and
  model weights; scan tracked/candidate source and known private credential literals.
  Screenshot review is visual; text scans are not universal DLP.

## Residual risks

The OS user, database owner and private signing/credential files remain trusted.
Local tokens are not MFA. There is no remote identity service, off-host sealed
audit store, distributed quota store or automated retention. Rotation does not
retroactively revoke already-issued exact grants; explicit expiry/revocation applies.
Not every denied HTTP operation is a durable audit event.

MCP disconnects may propagate SDK exception groups. Broad runs have had intermittent
connection/recovery timeouts. Investigation inference cannot resume after restart;
the durable action graph can. Package provenance, container OS CVEs and model weights
have not received an independent supply-chain audit.

Public hosting requires identity-aware TLS authentication for every route,
continued backend human authorization, isolated sandbox resources, restricted egress,
shared quotas, backup/restore evidence and a kill switch. Fault injection and
infrastructure-changing actions must never be anonymous. [Deployment requirements](DEPLOYMENT_ARCHITECTURE.md).
