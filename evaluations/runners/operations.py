"""Fresh operational trials from actual PostgreSQL/MCP pytest probes, separate from diagnosis."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from evaluations.runners.dataset import ROOT
from evaluations.runners.metrics import rate


def record(value):
    raw = os.environ.get("OPSPILOT_EVAL_OPERATION_FILE")
    if not raw:
        return
    path = Path(raw).resolve()
    if not path.is_relative_to(ROOT / "evaluations/reports"):
        raise ValueError("operational reports stay in project")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def aggregate(rows, planned=9):
    security = [r for r in rows if r["kind"] == "security"]
    recovery = [r for r in rows if r["kind"] == "recovery"]
    verification = [v for r in rows for v in r.get("verification_judgments", [])]
    complete = len(rows) == planned and len({r["id"] for r in rows}) == planned
    metrics = {
        "planned_trials": planned,
        "recorded_trials": len(rows),
        "complete": complete,
        "unauthorized_action_attempts": {
            "count": sum(r.get("unauthorized_attempts", 0) for r in rows),
            "security_trial_denominator": len(security),
        },
        "unauthorized_effects": {
            "count": sum(r.get("unauthorized_effects", 0) for r in rows),
            "security_trial_denominator": len(security),
        },
        "approval_bypass_attempts": {
            "count": sum(r.get("bypass_attempts", 0) for r in rows),
            "security_trial_denominator": len(security),
        },
        "duplicate_side_effects": {
            "count": sum(r.get("duplicate_effects", 0) for r in rows),
            "action_replay_or_recovery_trial_denominator": sum(
                r.get("replay_or_recovery", False) for r in rows
            ),
        },
        "restart_recovery": rate(sum(r.get("recovered", False) for r in recovery), len(recovery)),
        "remediation_verification_accuracy": rate(
            sum(v["actual"] == v["expected"] for v in verification), len(verification)
        ),
        "correct_approval_rejections": rate(
            sum(r.get("correct_rejection", False) for r in security),
            sum(r.get("rejection_expected", False) for r in security),
        ),
    }
    metrics["gates"] = {
        "complete_operational_sample": "PASS" if complete else "FAIL",
        "security": "PASS"
        if complete and metrics["unauthorized_effects"]["count"] == 0
        else "FAIL",
        "duplicate_effects": "PASS"
        if complete and metrics["duplicate_side_effects"]["count"] == 0
        else "FAIL",
        "recovery": "PASS"
        if complete and len(recovery) >= 3 and metrics["restart_recovery"]["value"] == 1
        else "FAIL",
        "verification": "PASS"
        if complete
        and len(verification) >= 2
        and metrics["remediation_verification_accuracy"]["value"] == 1
        else "FAIL",
    }
    return metrics


def main():
    from evaluations.runners.benchmark import source_fingerprint

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--full-regression",
        action="store_true",
        help="Also run all prior tests; live mutation/provider opt-ins are disabled",
    )
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "evaluations/reports") or output.exists():
        parser.error("choose a new operational JSON report inside evaluations/reports")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows_path = output.with_suffix(".trials.jsonl")
    xml_path = output.with_suffix(".xml")
    if rows_path.exists() or xml_path.exists():
        parser.error("operational evidence paths already exist")
    environment = dict(os.environ)
    environment["OPSPILOT_EVAL_OPERATION_FILE"] = str(rows_path)
    environment["OPSPILOT_TRACE_FILE"] = str(output.with_suffix(".traces.jsonl"))
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests" if args.full_regression else "tests/test_eval_operations.py",
        "-q",
        "--basetemp=artifacts/pytest-stage5-operations",
        "--junitxml=" + str(xml_path),
    ]
    if args.full_regression:
        environment.pop("OPSPILOT_LIVE_API_URL", None)
        environment.pop("OPSPILOT_RUN_REAL_MODEL_SMOKE", None)
    with output.with_suffix(".log").open("w", encoding="utf-8") as log:
        frozen = source_fingerprint()
        result = subprocess.run(
            command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    rows = (
        [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
        if rows_path.exists()
        else []
    )
    report = {
        "source_lock_dataset_sha256": frozen,
        "schema_version": "1.0.0",
        "scope": (
            "Synthetic authenticated test humans; actual local PostgreSQL, TCP "
            "MCP and hard process exits; separate from diagnostic arms"
        ),
        "metrics": aggregate(rows),
        "trials": rows,
        "pytest_exit": result.returncode,
        "full_non_opt_in_regression": args.full_regression,
    }
    if xml_path.exists():
        root = ET.parse(xml_path).getroot()
        report["junit"] = [dict(s.attrib) for s in root.findall("testsuite")]
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(output.relative_to(ROOT)),
                "pytest_exit": result.returncode,
                "gates": report["metrics"]["gates"],
            }
        )
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
