"""Positive export of actual release results; no raw diagnostic content or credentials."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    data = path.read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return json.loads(data.decode(encoding))


def pytest_counts(rows):
    counts = Counter()
    for row in rows:
        counts[
            "error" if row["outcome"] == "failed" and row["phase"] != "call" else row["outcome"]
        ] += 1
    return dict(counts)


def xml_counts(path):
    suite = ET.parse(path).getroot()
    if suite.tag == "testsuites":
        suite = suite.find("testsuite")
    return {
        k: float(suite.get(k, "0")) if k == "time" else int(suite.get(k, "0"))
        for k in ["tests", "failures", "errors", "skipped", "time"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "full",
        "rerun",
        "docker",
        "container_tests",
        "python_audit",
        "npm_audit",
        "hygiene",
        "release_tests",
    ]:
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--browser", type=Path, action="append", required=True)
    args = parser.parse_args()
    paths = [p for v in vars(args).values() for p in (v if isinstance(v, list) else [v])]
    for path in paths:
        if not path.resolve().is_relative_to(ROOT):
            parser.error("Use only this project's preserved evidence files")
    full, rerun = read_json(args.full), read_json(args.rerun)
    latest = {row["nodeid"]: row for row in full["tests"]}
    latest.update({row["nodeid"]: row for row in rerun["tests"]})
    browsers = []
    for path in args.browser:
        report = read_json(path)
        browsers.append({"source": path.as_posix(), "stats": report["stats"], "mode": "fixture"})
    py, npm, hygiene = [read_json(p) for p in [args.python_audit, args.npm_audit, args.hygiene]]
    value = {
        "schema_version": "portfolio-release-1",
        "stage": 8,
        "status": "CONDITIONAL",
        "real_model": {
            "configured": False,
            "attempted_evaluations": 0,
            "tokens": None,
            "cost_usd": None,
        },
        "python": {
            "full": pytest_counts(full["tests"]),
            "full_exit": full["exit_status"],
            "rerun": pytest_counts(rerun["tests"]),
            "rerun_exit": rerun["exit_status"],
            "latest_per_node": pytest_counts(list(latest.values())),
            "clean_full_run": full["exit_status"] == 0,
            "note": "One PG connection setup error passed unchanged in isolation; retained.",
        },
        "additional_release_tests": xml_counts(args.release_tests),
        "container_portable_tests": xml_counts(args.container_tests),
        "browser_runs": browsers,
        "clean_combined_browser_run": any(
            b["stats"].get("expected") == 6
            and b["stats"].get("unexpected") == 0
            and b["stats"].get("skipped") == 0
            for b in browsers
        ),
        "docker_startup": read_json(args.docker),
        "audits": {
            "python_packages": len(py["dependencies"]),
            "python_advisories": sum(len(d.get("vulns", [])) for d in py["dependencies"]),
            "python_unchecked_packages": sum("skip_reason" in d for d in py["dependencies"]),
            "npm_dependencies": npm["metadata"]["dependencies"]["total"],
            "npm_advisories": npm["metadata"]["vulnerabilities"],
        },
        "publication_scan": {
            "passed": hygiene["passed"],
            "mode": hygiene["inventory_mode"],
            "files": len(hygiene["files"]),
            "findings": len(hygiene["findings"]),
        },
        "ci": {
            "prepared": True,
            "github_executed": False,
            "permissions": "contents:read",
            "actions_sha_pinned": True,
        },
        "gates": {
            "real_model": "UNAVAILABLE",
            "historical_baseline_unsupported": "FAIL",
            "public_deployment": "NOT_READY",
            "publication": "CONDITIONAL_PREVIEW",
        },
        "benchmark": "benchmark-stage5.json (historical, not a current-source rerun)",
        "source_artifacts": [
            {"path": p.as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in paths
        ],
        "scope": "Actual local checks. No CI, cloud deployment, real LLM or superiority claim. "
        "Failed attempts/reruns remain separate; samples must not be pooled.",
    }
    target = ROOT / "docs/evidence/release-stage8.json"
    target.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": value["status"],
                "browser_clean": value["clean_combined_browser_run"],
                "audits": value["audits"],
            }
        )
    )


if __name__ == "__main__":
    main()
