"""Emit per-node review evidence from actual pytest results, including skips/errors."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reviews.stage7_catalog import CASES


def pytest_configure(config):
    config.stage7_rows = {}


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "teardown" and report.passed:
        return
    if report.when == "setup" and report.passed:
        return
    matches = [c for c in CASES if re.search(c[4], item.nodeid)]
    cases = [
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
    row = {
        "nodeid": item.nodeid,
        "phase": report.when,
        "outcome": report.outcome,
        "seconds": report.duration,
        "cases": cases
        or [
            {
                "id": "REG",
                "kind": "regression",
                "threat_or_failure_model": "Existing behavior regresses after security changes.",
                "procedure": "Execute " + item.nodeid,
                "expected": "All assertions in cited test pass.",
            }
        ],
        "actual": dict(report.user_properties),
        "evidence": item.location[0] + ":" + str(item.location[1] + 1),
    }
    if report.failed:
        # Failure bodies remain in separately redacted JUnit/logs, not this concise ledger.
        row["actual"]["result"] = (
            "Assertion/setup/teardown failed; inspect the redacted JUnit report."
        )
    elif report.skipped:
        row["actual"]["result"] = (
            str(report.longrepr[-1]) if isinstance(report.longrepr, tuple) else "Skipped"
        )
    else:
        row["actual"].setdefault(
            "result", "All assertions passed; expected control outcome observed."
        )
    item.config.stage7_rows[item.nodeid] = row


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("OPSPILOT_STAGE7_EVIDENCE")
    if not target:
        return
    root = Path(__file__).resolve().parents[1] / "artifacts" / "stage7"
    path = Path(target).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("review evidence must stay in the project Stage 7 artifact directory")
    value = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "exit_status": int(exitstatus),
        "tests": list(session.config.stage7_rows.values()),
    }
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
