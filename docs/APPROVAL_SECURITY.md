# Approval security

An LLM recommendation is untrusted input to a separate authorization boundary.
It is never a human decision. No approval issuance operation exists in MCP.
Stage 6 adds an authenticated loopback human-facing HTTP decision API behind the
Next.js BFF, reusing the exact-intent transaction. See [frontend architecture](FRONTEND_ARCHITECTURE.md).
The runtime has no unattended approval flag, approval boolean or model-accessible
terminal/file tool. The existing Stage 3 investigator remains read-only.

## Separate identities and capabilities

| Principal/process | Receives | Can do | Cannot do |
|---|---|---|---|
| Investigator | Seven-read MCP credential, optional model configuration | Diagnose and recommend | Approve or execute actions |
| Durable worker | `.runner.env`: runner DB credential and scoped executor token | Persist proposals/checkpoints, reconcile and deliver approved sandbox actions | Insert grants, set human decision fields, change faults directly, delete audits |
| Human operator CLI | Separate operator DB credential/key, hidden entered human token | Review, sign or revoke permitted requests | Directly change simulator faults or forge execution ledger records |
| MCP server | Caller registry hashes and delegation key | Validate/forward allowlisted requests | Read DB, issue grants or obtain signing/admin credentials |
| Authorization backend | Restricted DB role and approval verification key | Atomically validate/execute approved sandbox effects; bounded verification | Insert grants or change approver identity |

The local operator registry binds a high-entropy token digest, operator subject,
OS account, allowed services and named sandbox actions. The entered credential is
checked with constant-time digest comparison. The terminal process must use a real TTY;
the authenticated operator must type the exact action fingerprint phrase. The
approver identity is taken from that validated registry, not a model/tool argument.

The Stage 6 web path authenticates the registry credential and issues a revocable
30-minute HttpOnly session. Its approver comes exclusively from that session.
Browser decisions have no TTY requirement. The investigator receives none of the
human session, dashboard service key or decision endpoint capabilities.

Tests mock the TTY and secret prompt to represent **synthetic authenticated test
operators** in isolated databases. They do not claim that a real human attended
those tests, and those mocks are not runtime approval paths.

## Binding and integrity

A persistent request contains run ID, incident ID, exact proposed tool/arguments,
target service, risk, supporting observations and MCP request references, current
fault/generation/incident-event/metric versions, verification plan, expiration,
fingerprint, state, approver and approval/revocation timestamps.

The SHA-256 fingerprint hashes a canonical versioned intent envelope. It includes
the exact tool arguments except the fingerprint field itself, which is then added
to those arguments. The preallocated approval UUID and stable execution UUID are
included. Run, incident, target, evidence, risk, preconditions, expiry and measurement
plan are also bound. A separately issued HMAC-signed backend grant binds that
fingerprint and request UUID along with the original Stage 2 grant fields.

PostgreSQL triggers reject edits/deletion of immutable approval bindings and reject
invalid state transitions. Approver identity becomes immutable after the pending
decision. Audit events are append-only. Column privileges additionally prevent the
worker from inserting or updating human decision fields. Changing checkpoint
content cannot change the authoritative approval.

At execution, the backend independently validates caller scope, action feature
flag, signature, exact argument equality, run binding, expiry/revocation, one-use
state and resource preconditions under locks. A grant for one action cannot
authorize another tool, target, nonce, run or argument object. Revocation races
serialize with execution: whichever commits while holding the relevant locks
determines whether an effect occurs. Revocation cannot undo a committed action.

Pending/approved requests whose TTL elapsed are effectively `expired` even when
the stored decision field is still pending/approved; expiration does not depend on
a cleanup job. A repeated submission cannot renew it. Consumed historical grants
permit ledger reads and their already-approved measurement plan, never another
remediation. Revoked requests cannot be reapproved in place.

## Recovery authority

Execution and verification are different facts. A committed action can fail its
health check. The graph records `failed`/`inconclusive` and executes no follow-up
remediation. A recovery has a new run, new action fingerprint and new operator
decision, and revalidates current evidence and preconditions. A graph wake-up,
retry, old approval UUID or previous run's checkpoint cannot supply that authority.

## Limits of the local human boundary

This design trusts the local operator's OS account, private credential files and
database administrators. A TTY is not cryptographic proof of physical human
presence. A process already able to steal the human signing/DB credentials and
control that account could impersonate its operator. The model receives none of
those capabilities. This is the same explicit host trust boundary as Stage 2,
with separate database privileges and stronger run/action binding added.

For multi-user or remotely hosted use, replace the local terminal identity with
an independently operated identity/approval service, strong operator authentication
and protected key storage. No such deployment is claimed here. PostgreSQL owners
can change schemas/triggers; protection against a malicious database owner is not
claimed. Checkpoint storage must remain private even with safe deserialization.

## Stage 7 handoff and session hardening

An MCP request ID and real metric reference alone do not attest the quantities in
an investigation. Before approval creation, the repository reconstructs cited
metric/log/deployment/incident projections from stored simulator rows and checks
their exact content and resource binding. Altered data fails with
`EVIDENCE_CONTENT_MISMATCH`. This authenticates cited facts, not causal reasoning
or the correctness of model prose. The database owner remains trusted.

Web session digests are bound to the current human credential, subject and OS
account. Rotation invalidates old and legacy cookies; login is required again.
Current registry permissions apply on every lookup. This does not retroactively
revoke an already-issued exact grant; explicit grant revocation/expiry still applies.

The action allowlist contains only the three reversible fictional simulator tools.
No production credentials, arbitrary commands, SQL, shell, unrestricted files,
cloud actions or irreversible remediation are exposed. All MCP results retain
typed bounded envelopes and untrusted-data markings. The administrative audit
export is separate from the model/tool response surface.
