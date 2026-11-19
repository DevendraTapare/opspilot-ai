"""Publish aggregates from actual Stage 9 evidence, never raw credentials/content."""

import argparse
import hashlib
import json
import statistics
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(inspection_path, operations_path, rechecks=()):
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    operations = json.loads(operations_path.read_text(encoding="utf-8"))
    benchmarks = {}
    for name in [
        "calibration-before",
        "calibration-after",
        "heldout-before",
        "heldout-after",
        "fixture-calibration",
    ]:
        path = ROOT / "evaluations/reports" / ("stage9-" + name + ".json")
        report = json.loads(path.read_text(encoding="utf-8"))
        attempted = [t for t in report["trials"] if t["prediction"]["status"] != "excluded"]
        benchmarks[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": digest(path),
            "source_lock_dataset_sha256": report["frozen_plan"]["source_lock_dataset_sha256"],
            "metrics": report["metrics"],
            "gates": report["gates"],
            "mean_attempted_latency_ms": statistics.mean(t["elapsed_ms"] for t in attempted),
            "tool_outcomes": dict(
                Counter(c["outcome"] for t in report["trials"] for c in t["tool_calls"])
            ),
            "release_ready": False,
        }
    history = {
        name: digest(ROOT / name) == value
        for name, value in inspection["protected_history_sha256"].items()
    }
    xml_path = ROOT / operations["evidence_directory"] / "pytest.xml"
    current_skips, errors = [], []
    for case in ET.parse(xml_path).iter("testcase"):
        node = case.get("classname") + "::" + case.get("name")
        if (skip := case.find("skipped")) is not None:
            reason = skip.get("message", "")
            current_skips.append(
                {
                    "node": node,
                    "reason": reason,
                    "classification": "Optional external dependency"
                    if "Real-model" in reason or "Running API" in reason
                    else "Expected environment limitation"
                    if "PostgreSQL" in reason
                    else "Unresolved defect",
                }
            )
        if (error := case.find("error")) is not None:
            errors.append(
                {
                    "node": node,
                    "classification": "PostgreSQL connection timeout during setup"
                    if "ConnectionTimeout" in (error.text or "")
                    else "Unclassified setup error",
                    "source": xml_path.relative_to(ROOT).as_posix(),
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "verdict": "BLOCKED — REAL MODEL UNAVAILABLE",
        "real_model": {
            "provider": None,
            "model": None,
            "attempted_cases": 0,
            "accuracy": None,
            "tokens": None,
            "estimated_api_cost_usd": None,
        },
        "sample_note": "Rules/fixture only; old held-out is replay after inspection.",
        "benchmarks": benchmarks,
        "operations": {
            "path": operations_path.relative_to(ROOT).as_posix(),
            "sha256": digest(operations_path),
            **operations,
        },
        "separate_rechecks": [
            {
                "path": p.relative_to(ROOT).as_posix(),
                "sha256": digest(p),
                "report": json.loads(p.read_text(encoding="utf-8")),
            }
            for p in rechecks
        ],
        "current_regression_skips": current_skips,
        "current_regression_errors": errors,
        "initial_evidence_writer_error": (
            "Stage 7 plugin rejected Stage 9 output after tests; full cases.json absent. "
            "Fixed with dedicated Stage 9 writer; JUnit/trial evidence retained."
        ),
        "historical_skip_ledger": inspection["historical_skips"],
        "protected_history": {"all_unchanged": all(history.values()), "files": history},
        "limitations": [
            "No real model inference, safety, durability handoff or UI validation.",
            "Calibration correctness failed; old held-out is not unbiased after tuning.",
            "Read broad-run errors alongside focused reruns; no pooled pass count.",
            "Operations use deterministic proposals and synthetic humans, not model reasoning.",
        ],
        "release_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--operations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recheck", type=Path, action="append", default=[])
    args = parser.parse_args()
    inspection, operations, output = (
        p.resolve() for p in [args.inspection, args.operations, args.output]
    )
    rechecks = [p.resolve() for p in args.recheck]
    if (
        not inspection.is_relative_to(ROOT / "artifacts/stage9")
        or not operations.is_relative_to(ROOT / "evaluations/reports")
        or not output.is_relative_to(ROOT / "docs/evidence")
        or output.exists()
        or any(not p.is_relative_to(ROOT / "evaluations/reports") for p in rechecks)
    ):
        parser.error("Use Stage 9 inspection/operations evidence and a new docs/evidence output")
    result = summarize(inspection, operations, rechecks)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output.relative_to(ROOT)),
                "history_unchanged": result["protected_history"]["all_unchanged"],
                "verdict": result["verdict"],
            }
        )
    )


if __name__ == "__main__":
    main()
