"""Preserved full regression with isolated PostgreSQL and separate operational metrics."""

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from evaluations.runners.benchmark import source_fingerprint
from evaluations.runners.operations import aggregate
from scripts.review_stage9 import environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", action="append", default=[], help="Exact test node/file recheck")
    args = parser.parse_args()
    for node in args.node:
        path = (ROOT / node.split("::")[0]).resolve()
        if not path.is_relative_to(ROOT / "tests") or not path.is_file():
            parser.error("Only existing project test files/nodes may be selected")
    run = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    folder = ROOT / "artifacts/stage9" / run
    folder.mkdir(parents=True, exist_ok=False)
    output = ROOT / "evaluations/reports" / ("stage9-operations-" + run + ".json")
    trials = output.with_suffix(".trials.jsonl")
    env = environment()
    env.update(
        OPSPILOT_STAGE7_CONTAINER_RESTART="1",
        OPSPILOT_STAGE9_EVIDENCE=str(folder / "cases.json"),
        OPSPILOT_EVAL_OPERATION_FILE=str(trials),
    )
    frozen = source_fingerprint()
    print("Stage 9 full regression: " + str(folder.relative_to(ROOT)), flush=True)
    start = time.monotonic()
    with (folder / "pytest.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *(args.node or ["tests"]),
                "-p",
                "reviews.stage9_plugin",
                "-q",
                "-o",
                "junit_family=legacy",
                "--basetemp=" + str(folder / "tmp"),
                "--junitxml=" + str(folder / "pytest.xml"),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    rows = [json.loads(line) for line in trials.read_text().splitlines()] if trials.exists() else []
    counts = {"passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    if (folder / "pytest.xml").exists():
        for case in ET.parse(folder / "pytest.xml").iter("testcase"):
            category = next(
                (
                    k
                    for k, tag in [
                        ("errors", "error"),
                        ("failures", "failure"),
                        ("skipped", "skipped"),
                    ]
                    if case.find(tag) is not None
                ),
                "passed",
            )
            counts[category] += 1
    report = {
        "source_lock_dataset_sha256": frozen,
        "finished_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic operational tests; real MCP/PostgreSQL; no LLM inference",
        "pytest_exit": result.returncode,
        "selection": args.node or ["tests"],
        "counts": counts,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "evidence_directory": folder.relative_to(ROOT).as_posix(),
        "metrics": aggregate(rows),
        "trials": rows,
        "real_model_cases": 0,
        "release_ready": False,
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"report": str(output.relative_to(ROOT)), "exit": result.returncode, "counts": counts}
        ),
        flush=True,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
