"""Combine held-out diagnostics with contemporaneous operational checks; fail closed."""

import argparse
import json
from pathlib import Path

from evaluations.runners.contracts import Trial
from evaluations.runners.dataset import ROOT, load
from evaluations.runners.metrics import gates


def assess(diagnostic, operational):
    same_source = diagnostic["frozen_plan"]["source_lock_dataset_sha256"] == operational.get(
        "source_lock_dataset_sha256"
    )
    selected = diagnostic["frozen_plan"]["case_ids"]
    is_final = (
        diagnostic["split"] == "held_out"
        and len(selected) == len(set(selected)) == 40
        and set(selected) == {c.id for c in load("held_out")}
    )
    results = {}
    operational_ok = operational.get("pytest_exit") == 0 and all(
        v == "PASS" for v in operational["metrics"]["gates"].values()
    )
    for arm in ["llm", "structured"]:
        metrics = diagnostic["metrics"].get(arm)
        real = bool(diagnostic["model"]["available"] and not diagnostic["model"]["fixture_smoke"])
        checks = gates(metrics, real=real, operations=operational["metrics"]) if metrics else []
        checks.extend(
            [
                {
                    "name": "operational_security_and_verification",
                    "status": "PASS" if operational_ok else "FAIL",
                },
                {
                    "name": "matched_source_and_complete_heldout",
                    "status": "PASS" if same_source and is_final else "FAIL",
                },
            ]
        )
        rows = [Trial.model_validate(t) for t in diagnostic["trials"] if t["arm"] == arm]
        attempts = sum(t.prediction.status != "excluded" for t in rows)
        timeouts = sum(t.prediction.status == "timeout" for t in rows)
        checks.append(
            {
                "name": "timeout_rate",
                "observed": timeouts / attempts if attempts else None,
                "requirement": "timeouts / attempted <= 0.05",
                "status": "UNAVAILABLE"
                if not attempts
                else "PASS"
                if timeouts / attempts <= 0.05
                else "FAIL",
            }
        )
        results[arm] = {
            "gates": checks,
            "release_ready": bool(metrics) and all(c["status"] == "PASS" for c in checks),
        }
    return {
        "schema_version": "1.0.0",
        "arms": results,
        "same_source": same_source,
        "complete_heldout": is_final,
        "release_ready": all(r["release_ready"] for r in results.values()),
        "note": "FAIL and UNAVAILABLE block release. No model superiority is inferred.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--held-out", required=True)
    parser.add_argument("--operations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paths = [Path(p).resolve() for p in [args.held_out, args.operations, args.output]]
    if not all(p.is_relative_to(ROOT / "evaluations/reports") for p in paths) or paths[2].exists():
        parser.error("use existing input reports and a new output inside evaluations/reports")
    report = assess(*[json.loads(p.read_text(encoding="utf-8")) for p in paths[:2]])
    paths[2].write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"release_ready": report["release_ready"], "report": str(paths[2].relative_to(ROOT))}
        )
    )
    raise SystemExit(0 if report["release_ready"] else 1)


if __name__ == "__main__":
    main()
