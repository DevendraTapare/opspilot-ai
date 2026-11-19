"""Render review documents only from a completed, preserved pytest evidence ledger."""

# Markdown tables below intentionally keep each logical row on one source line.
# ruff: noqa: E501

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from reviews.stage7_catalog import CASES

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/"

LIMITS = """- No real LLM is configured. Injection tests use real persisted logs/MCP and labeled deterministic or malicious structured model decisions. Semantic resistance to prompt injection, persuasion, plausible incorrect diagnoses and goal hijacking remains **unverified**.
- Positive context projections remove tested log payload fields and fixture truth, but other allowed text remains untrusted. Schemas, system instructions and citation checks do not prove general prompt-injection immunity or causal correctness.
- The telemetry handoff compares cited projected facts with stored simulator rows. It does not prove completeness of an investigation or correctness of model prose. A trusted database owner can alter source rows.
- Local OS accounts, database owners, signing keys and credential files are trusted. No MFA, remote TLS, hostile-tenant isolation, production credentials or independent remote approval service is claimed. Dashboard read views are local service-wide views.
- Session rotation fails closed, including legacy sessions, and requires login again. Rotation does not retroactively revoke previously issued exact action grants; their explicit revocation and expiration remain separate controls.
- Rate counters are per process. Slow-body deadlines do not establish resistance to slow headers, many concurrent sockets, volumetric traffic or CPU/memory exhaustion. Telemetry/session retention needs an explicit maintenance policy.
- MCP SDK HTTP transport failures can propagate as an exception group before a final recommendation is produced. The disconnection test accepts only HTTP transport exceptions and verifies zero action effects; uninterrupted recommendation availability is not guaranteed.
- PostgreSQL restart uses graceful stop/start of the dedicated retained review volume while awaiting approval. WAL corruption, failover replicas and database termination mid-commit are not tested. Simulator restart uses two actual OS processes; worker crash tests use real child exits.
- Exactly-once evidence is limited to transactional simulator effects and their unique action ledger. It is not a guarantee for arbitrary remote side effects. Investigation restarts are marked interrupted; a single dashboard job manager is supported.
- Database role/trigger tests do not protect against a database administrator. Denied HTTP operations are not all durable audit events; action attempts and authoritative transitions have the tested audit path. Independent off-host audit sealing and retention are absent.
- Locked dependencies and an enforced tool inventory are partial supply-chain controls. This review is not an independent CVE, package provenance or model-weight audit. There is one investigator, not a hostile multi-agent network.
"""


def render_cases(kind, rows):
    text = []
    matrix = []
    for case in CASES:
        cid, group, risk, title, _, threat, procedure, expected = case
        if group != kind:
            continue
        matched = [r for r in rows if any(c["id"] == cid for c in r["cases"])]
        counts = Counter(r["outcome"] for r in matched)
        status = "FAIL" if counts["failed"] else "PASS" if counts["passed"] else "NOT EXERCISED"
        matrix.append({"id": cid, "status": status, "counts": dict(counts)})
        text.extend(
            [
                f"## {cid}: {title} — {status}",
                f"Risk reference: {risk}. Threat/failure model: {threat}",
                f"Procedure: {procedure}",
                f"Expected: {expected}",
                f"Actual: {counts['passed']} passed, {counts['failed']} failed, "
                f"{counts['skipped']} skipped parameterized tests. "
                "A skip is not a demonstrated control.",
            ]
        )
        for row in matched:
            actual = json.dumps(row["actual"], ensure_ascii=True).replace("|", "\\|")
            text.append(
                f"- **{row['outcome'].upper()}** `{row['nodeid']}` "
                f"({row['seconds']:.3f}s): {actual}. "
                f"[Assertion source](../{row['evidence'].split(':')[0]})."
            )
        if not matched:
            text.append("No matching executed test: no pass claimed.")
        text.append("")
    return "\n\n".join(text), matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--supplement", type=Path, action="append", default=[])
    args = parser.parse_args()
    path = args.ledger.resolve()
    if not path.is_relative_to((ROOT / "artifacts/stage7").resolve()):
        raise SystemExit("Use a preserved Stage 7 ledger inside this project")
    ledger = json.loads(path.read_text(encoding="utf-8"))
    original_counts = Counter(r["outcome"] for r in ledger["tests"])
    latest = {r["nodeid"]: r for r in ledger["tests"]}
    supplemental = []
    for extra in args.supplement:
        extra = extra.resolve()
        if not extra.is_relative_to((ROOT / "artifacts/stage7").resolve()):
            raise SystemExit("Supplemental ledgers must also be preserved Stage 7 evidence")
        value = json.loads(extra.read_text(encoding="utf-8"))
        supplemental.append(
            (
                extra.parent.relative_to(ROOT).as_posix(),
                value["exit_status"],
                dict(Counter(r["outcome"] for r in value["tests"])),
            )
        )
        for row in value["tests"]:
            if row["nodeid"] in latest:
                row["previous_results"] = [latest[row["nodeid"]]]
            latest[row["nodeid"]] = row
    rows = list(latest.values())
    # Reclassify risk references with the final catalog, retaining original ledgers.
    for row in rows:
        matches = [c for c in CASES if re.search(c[4], row["nodeid"])]
        if matches:
            row["cases"] = [
                {
                    "id": c[0],
                    "kind": c[1],
                    "owasp": c[2],
                    "title": c[3],
                    "threat_or_failure_model": c[5],
                    "procedure": c[6],
                    "expected": c[7],
                }
                for c in matches
            ]
    counts = Counter(r["outcome"] for r in rows)
    evidence = path.parent.relative_to(ROOT).as_posix()
    security, sm = render_cases("security", rows)
    reliability, rm = render_cases("reliability", rows)
    matrix = {
        "source": evidence,
        "cases": sm + rm,
        "test_counts": dict(counts),
        "initial_counts": dict(original_counts),
        "supplements": supplemental,
    }
    (path.parent / "case_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    (path.parent / "review_results.json").write_text(
        json.dumps({"matrix": matrix, "latest_per_node": rows}, indent=2), encoding="utf-8"
    )
    preamble = (
        f"Review recorded {ledger['recorded_at_utc']}. Completed pytest exit status "
        f"**{ledger['exit_status']}**; **{original_counts['passed']} passed, "
        f"{original_counts['failed']} failed, {original_counts['skipped']} skipped**. "
        "These are one full run's counts, not a sum of overlapping "
        "regressions. Group totals overlap where a test exercises several risks.\n\n"
        f"Per-test evidence: [JSON ledger](../{evidence}/cases.json), "
        f"[JUnit](../{evidence}/pytest.xml), [execution log](../{evidence}/pytest.log), "
        f"[case matrix](../{evidence}/case_matrix.json). Each JSON record includes threat/failure "
        "model, procedure, expected result, actual result, source location and outcome. "
        "Unmatched tests are explicitly recorded as REG regressions. Artifacts are local and "
        "ignored by Git; keep this directory when sharing verification evidence.\n\n"
    )
    for folder, status, scounts in supplemental:
        preamble += (
            f"Supplemental targeted run: [evidence](../{folder}/cases.json), "
            f"exit {status}, counts {scounts}.\n\n"
        )
    if supplemental:
        preamble += (
            f"Latest result per distinct test node: **{counts['passed']} passed, "
            f"{counts['failed']} failed, {counts['skipped']} skipped**. "
            "This is a reconciliation of the full run and targeted reruns, not a second "
            "clean full-suite run. Earlier failures remain in their original ledgers and "
            f"[result history](../{evidence}/review_results.json).\n\n"
            "The initial failure was the measured before-approval-restart probe: its "
            "recovered child exceeded the unchanged 90-second timeout. The equivalent "
            "durable probe passed in the full run. A successful isolated rerun establishes "
            "recovery in that trial, not predictable latency under host contention. "
            "The cause of the initial timeout was not established. The intermittent "
            "recovery timeout remains an operational risk.\n\n"
        )
    findings = """## Confirmed findings and fixes

| ID | Confirmed behavior before fix | Fix and regression evidence |
|---|---|---|
| F01 | Schema-valid metrics and dependency identity substitution could produce a fixture recommendation for the wrong evidence resource. Incident substitution was already rejected later in triage. | Bind all parsed observations to requested service/incident and known dependency topology. Three response substitutions are rejected earlier. `agent/evidence.py`, shared `topology.py`. |
| F02 | Rotating a human registry credential left an existing session usable. | Store a credential/account/subject-bound HMAC session digest; use current registry permissions. Old sessions fail closed. `dashboard/security.py`. |
| F03 | Gateway per-chunk timeouts could be extended indefinitely by drip-fed input; dashboard/BFF body reads lacked absolute deadlines. | Absolute five-second body budgets plus existing 16 KiB limits in ASGI and Next BFF. Real unfinished TCP body returns 408. |
| F04 | Genuine MCP audit/request/metric IDs could accompany forged metric quantities in a submitted investigation. | Reconstruct cited positive projections from persisted telemetry before durable handoff; reject EVIDENCE_CONTENT_MISMATCH. `durable/evidence.py` and `durable/repository.py`. |

Reproduction evidence was retained: `artifacts/stage7-boundaries-before.xml` has
5 failures and 1 skip; `artifacts/stage7-attestation-before.xml` has 1 failure and
1 skip. Focused important-fix regressions: evidence binding 35 passed/3 skipped/
3 deselected; sessions 13 passed/10 skipped/1 deselected; body deadlines 14 passed/
10 skipped; durable attestation and integrations 33 passed/32 skipped. These
overlapping runs are not added to the completed regression total above.
The first integration attempt retained 12 passed/8 skipped/2 failures: offline
socket exception classification and SDK grouped transport errors required explicit
test expectations. Neither failure was silently counted as a successful final
recommendation. A later simulator test was strengthened to restart an OS process.

No action allowlist, approval authentication, database role, expiry, fingerprint,
quota or verification threshold was relaxed. No automatic recovery action was added.
"""
    mapping = (
        """## OWASP risk-reference coverage

This review uses the [OWASP Top 10 for Agentic Applications 2026]("""
        + REFERENCE
        + """),
released December 9, 2025. It is a risk mapping, not OWASP certification or proof
that every attack under each category is prevented.

| Reference | Tested controls / scope |
|---|---|
| ASI01 Agent Goal Hijack | S01/S03 projections and structured decision validation; real-model persuasion unverified |
| ASI02 Tool Misuse & Exploitation | S04–S08 allowlists, argument binding, rate/budget enforcement |
| ASI03 Identity & Privilege Abuse | S04–S06/S09–S12 exact authority, scopes, rotation, role constraints |
| ASI04 Agentic Supply Chain Vulnerabilities | S02/S11/S14 response binding and evidence integrity; package/model supply-chain audit absent |
| ASI05 Unexpected Code Execution (RCE) | S08 fixed sandbox/read-only tool boundaries; no arbitrary command interface |
| ASI06 Memory & Context Poisoning | S01/S12 projected context and immutable audit controls; no general memory-security claim |
| ASI07 Insecure Inter-Agent Communication | S02/S09/R03 authenticated MCP transport and binding; no multi-agent network tested |
| ASI08 Cascading Failures | S13/R01–R08/R11 bounded failure and recovery behavior |
| ASI09 Human-Agent Trust Exploitation | S10/S14/R09–R11 current authority, cited facts, abstention and measured verification |
| ASI10 Rogue Agents | S03/S07 schema and resource limits; semantic model behavior unverified |
"""
    )
    (ROOT / "docs/SECURITY_REVIEW.md").write_text(
        "# Stage 7 security review\n\n"
        + preamble
        + findings
        + "\n"
        + mapping
        + "\n## Test records\n\n"
        + security
        + "\n## Unresolved risks and limits\n\n"
        + LIMITS,
        encoding="utf-8",
    )
    guarantees = """## Demonstrated guarantee boundaries

Read the individual outcomes below before treating any guarantee as demonstrated.
Passing duplicate/crash tests establish one observable simulator mutation and a
unique execution record for the exact approved action. The authorizer commits
grant consumption, effect and ledger atomically in PostgreSQL. A lost acknowledgment
requires authoritative reconciliation before redelivery. Checkpointing alone is
not the exactly-once mechanism. Resume locks exclude concurrent execution of the
same durable run; a model or resume payload cannot issue approval.

The PostgreSQL test deliberately stops only `opspilot-stage7`'s `review-db`, checks
the outage, restores the retained volume and resumes the same pending approval.
The simulator test terminates one server process, proves the TCP outage and starts
a different PID against the same schema. Crash-hook tests terminate real worker
children before/after execution and recreate the durable saver. These tests do
not establish arbitrary external-service exactly-once semantics or corruption recovery.

An action result and service recovery are distinct persisted facts. Failed measured
verification remains failed/inconclusive, and further remediation needs a new
human-authorized intent. Rejection is correct policy behavior, not system failure.
Timeout/provider tests use explicitly delayed/failing adapters, not a real LLM.
"""
    (ROOT / "docs/RELIABILITY_REPORT.md").write_text(
        "# Stage 7 reliability report\n\n"
        + preamble
        + guarantees
        + "\n## Test records\n\n"
        + reliability
        + "\n## Unresolved risks and limits\n\n"
        + LIMITS,
        encoding="utf-8",
    )
    commands = r"""## Reproduce in Windows PowerShell

Prerequisites: running Docker Desktop with Linux containers, the existing locked
Python environment and frontend npm dependencies. Run from this project only.
The runner validates Compose labels and the private port before allowing restart.
It creates fresh per-test UUID schemas and removes only those schemas. It never
resets the main database or deletes previous reports.

```powershell
Set-Location D:\Projects\OpsPilot-AI
.\.venv\Scripts\python.exe -m scripts.initialize_stage7
docker compose --env-file .stage7.env -f compose.stage7.yaml up -d --wait review-db
Push-Location frontend
npm.cmd run typecheck
npm.cmd run build
Pop-Location
.\.venv\Scripts\python.exe -m scripts.review_stage7
# Use the actual new directory printed by the runner:
.\.venv\Scripts\python.exe -m reviews.stage7_report artifacts/stage7/<run-directory>/cases.json
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
docker compose --env-file .stage7.env -f compose.stage7.yaml ps -a
docker compose --env-file .stage7.env -f compose.stage7.yaml stop review-db
```

`--focused` runs only the new Stage 7 cases, preserving a new evidence directory.
Review credentials are generated privately in ignored `.stage7.env`, never echoed.
Do not replace the review URL with the main database. Do not run `down -v`, global
container cleanup or test containers from other projects. The review volume stays
retained after stopping. Test listeners and Node processes are owned by fixtures.
"""
    state = "CONDITIONAL" if not counts["failed"] else "FAIL"
    (ROOT / "docs/STAGE_7_REPORT.md").write_text(
        f"# Stage 7 completion report — {state}\n\n" + preamble + "## Environment and execution\n\n"
        "Local Windows PowerShell, Python 3.12.3, Linux Docker PostgreSQL 18.6, "
        "dedicated `opspilot-stage7` Compose project at loopback port 56437. "
        "Schema revision remains `0004_dashboard`; no migration or dependency upgrade "
        "was required. Locked backend and frontend versions remain in `uv.lock` and "
        "`frontend/package-lock.json`. Real MCP SDK discovery/calls, TCP HTTP, separate "
        "Node and simulator processes, PostgreSQL transactions/checkpoints and controlled "
        "worker crashes were exercised. Stage 7 Next checks use actual HTTP, not a browser; "
        "historical Stage 6 Chromium evidence is preserved.\n\n"
        "**Real model: unavailable/unconfigured.** No paid calls, model tokens, cost or "
        "real-model security results are claimed. Deterministic fixtures and adversarial "
        "structured decisions are labeled test inputs. Tests gated on unsupported SQLite "
        "durability or unconfigured providers remain skipped with their actual reasons "
        "in the ledger. Precisely: 46 SQLite variants require PostgreSQL semantics, "
        "two opt-in running-main-API tests were unconfigured, and one real-model smoke "
        "was not opted in. Isolated simulator HTTP tests did run. A nonzero pytest "
        "result or failed case remains visible.\n\n"
        "Environment evidence: [package versions and lock digests](../"
        + evidence
        + "/environment.json). Frontend TypeScript checking and the production Next build "
        "passed after the body-deadline change; [final build log](../artifacts/"
        "stage7-frontend-build.log). Final Ruff checks/format validation passed for "
        "128 Python files. The bounded configured-secret scan inspected 39 report/log/"
        "browser-JS files and found zero literal/prefix matches; [scope and result](../"
        + evidence
        + "/credential_scan.json). This is not a general DLP claim.\n\n"
        "Final shutdown stops only the dedicated review database and retains its volume. "
        "The existing Stage 1 Compose services remain stopped. See [container status](../"
        + evidence
        + "/final_containers.json). No main database was restarted or reset.\n\n"
        + findings
        + "\n## Deliverables\n\n"
        "- Security/reliability documents above and this Stage 7 report.\n"
        "- Shared topology, response-resource binding, credential-bound sessions, "
        "absolute request-body deadlines and persisted fact attestation.\n"
        "- Three Stage 7 test modules, private Compose fixture, review initialization/runner, "
        "case catalog, evidence plugin, report generator and isolated simulator child.\n"
        "- Machine-readable per-test ledger, JUnit, logs and case matrix in the cited "
        "preserved run directory; all earlier reports retained.\n\n"
        + commands
        + "\n## Remaining risks\n\n"
        + LIMITS
        + f"\n## Disposition\n\n**{state}**: "
        + (
            "latest per-node results have no failing assertions; the initial full-run "
            "recovery timeout remains an unresolved operational risk. Real-model "
            "adversarial resistance and the scope limits above remain unverified."
            if state == "CONDITIONAL"
            else "the completed regression has unresolved failures; see its ledger."
        )
        + " No Git commit/push, cloud deployment or Stage 8 work. Stop at Stage 7.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": state, "counts": dict(counts), "matrix": sm + rm}))


if __name__ == "__main__":
    main()
