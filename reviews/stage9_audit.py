"""Content-free configuration inventory and complete historical skip classification."""

import hashlib
import json
import os
import platform
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "regression": "artifacts/stage7/20261104T112126Z-8038c0/pytest.xml",
    "docker": "artifacts/stage8/docker-portable/pytest.xml",
}


def historical_skips():
    records = []
    for suite, path in SOURCES.items():
        for case in ET.parse(ROOT / path).iter("testcase"):
            skip = case.find("skipped")
            if skip is None:
                continue
            reason = skip.get("message", "")
            category = (
                "Optional external dependency"
                if "Real-model" in reason or "Running API" in reason
                else "Expected environment limitation"
                if "PostgreSQL" in reason
                else "Unresolved defect"
            )
            records.append(
                {
                    "suite": suite,
                    "source": path,
                    "node": case.get("classname") + "::" + case.get("name"),
                    "reason": reason,
                    "classification": category,
                }
            )
    return {
        "records": records,
        "counts": {
            suite: dict(Counter(r["classification"] for r in records if r["suite"] == suite))
            for suite in SOURCES
        },
    }


def capture():
    keys = ["OPSPILOT_AGENT_" + k for k in ["PROVIDER", "MODEL", "BASE_URL", "API_KEY"]]
    presence = {"process": {k: bool(os.environ.get(k)) for k in keys}}
    for path in sorted(ROOT.glob(".*env")):
        if path.is_file():
            values = dotenv_values(path)
            presence[path.name] = {k: bool(values.get(k)) for k in keys}
    endpoints = {}
    # Only fixed loopback discovery endpoints; never send credentials or follow proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name, url in {
        "ollama": "http://127.0.0.1:11434/api/tags",
        "lm_studio": "http://127.0.0.1:1234/v1/models",
    }.items():
        try:
            with opener.open(url, timeout=3) as response:
                data = json.loads(response.read(65536))
            endpoints[name] = {
                "reachable": True,
                "models": [
                    v.get("name", v.get("id")) for v in data.get("models", data.get("data", []))
                ][:20],
            }
        except (urllib.error.URLError, OSError, ValueError):
            endpoints[name] = {"reachable": False, "models": []}
    protected = [
        *ROOT.glob("docs/STAGE_*_REPORT.md"),
        *[
            p
            for p in (ROOT / "evaluations/reports").glob("*.json")
            if not p.name.startswith("stage9-")
        ],
        ROOT / "evaluations/datasets/v1/manifest.json",
        *ROOT.glob("evaluations/datasets/v1/*.jsonl"),
    ]
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "configuration_presence_only": presence,
        "local_model_endpoints": endpoints,
        "local_executable_presence": {
            k: shutil.which(k) is not None for k in ["ollama", "lms", "nvidia-smi"]
        },
        "project_disk_free_bytes": shutil.disk_usage(ROOT).free,
        "protected_history_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(protected)
        },
        "historical_skips": historical_skips(),
    }


def main():
    folder = (
        ROOT
        / "artifacts/stage9"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    data = capture()
    (folder / "inspection.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(folder.relative_to(ROOT).as_posix())
    print(json.dumps(data["historical_skips"]["counts"]))


if __name__ == "__main__":
    main()
