"""Run an isolated review; preserve every run directory and all previous stage reports."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", action="store_true")
    parser.add_argument("--node", action="append", default=[], help="Exact pytest node to rerun")
    args = parser.parse_args()
    if args.focused and args.node:
        parser.error("Choose --focused or --node")
    for node in args.node:
        file = (ROOT / node.split("::")[0]).resolve()
        if not file.is_relative_to(ROOT / "tests") or not file.is_file() or file.suffix != ".py":
            parser.error("Only existing test files inside this project may be selected")
    values = dotenv_values(ROOT / ".stage7.env")
    identity = subprocess.run(
        ["docker", "inspect", "opspilot-stage7-review-db-1"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    container = json.loads(identity.stdout)[0]
    labels = container["Config"]["Labels"]
    if (
        labels["com.docker.compose.project"] != "opspilot-stage7"
        or labels["com.docker.compose.service"] != "review-db"
    ):
        raise SystemExit("Refusing any database other than the dedicated Stage 7 container")
    port = int(values["STAGE7_DB_PORT"])
    if int(container["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]) != port:
        raise SystemExit("Review database port does not match its private configuration")
    run = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    folder = ROOT / "artifacts/stage7" / run
    folder.mkdir(parents=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPSPILOT_", "POSTGRES_", "LANGSMITH_", "LANGCHAIN_"))
    }
    env.update(
        OPSPILOT_TEST_DATABASE_URL=URL.create(
            "postgresql+psycopg",
            username="opspilot_test",
            password=values["STAGE7_POSTGRES_PASSWORD"],
            host="127.0.0.1",
            port=port,
            database="opspilot_stage1_test",
        ).render_as_string(hide_password=False),
        OPSPILOT_STAGE7_CONTAINER_RESTART="1",
        OPSPILOT_STAGE7_EVIDENCE=str(folder / "cases.json"),
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    files = args.node or (
        [
            "tests/test_stage7_boundaries.py",
            "tests/test_stage7_integrations.py",
            "tests/test_stage7_frontend.py",
        ]
        if args.focused
        else ["tests"]
    )
    print("Stage 7 evidence directory: " + str(folder.relative_to(ROOT)), flush=True)
    with (folder / "pytest.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *files,
                "-p",
                "reviews.stage7_plugin",
                "-q",
                "-o",
                "junit_family=legacy",
                "--basetemp=" + str(folder / "tmp"),
                "--junitxml=" + str(folder / "pytest.xml"),
            ],
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    print("Actual pytest exit status: " + str(result.returncode), flush=True)
    if (folder / "cases.json").exists():
        records = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
        from collections import Counter

        print(json.dumps(dict(Counter(t["outcome"] for t in records["tests"]))), flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
