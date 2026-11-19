"""Stage 9 benchmark wrapper: isolated review DB, new reports, no model substitution."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


def environment():
    values = dotenv_values(ROOT / ".stage7.env")
    result = subprocess.run(
        ["docker", "inspect", "opspilot-stage7-review-db-1"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    container = json.loads(result.stdout)[0]
    labels = container["Config"]["Labels"]
    port = int(values["STAGE7_DB_PORT"])
    if (
        labels.get("com.docker.compose.project") != "opspilot-stage7"
        or labels.get("com.docker.compose.service") != "review-db"
        or not container["State"]["Running"]
        or int(container["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]) != port
    ):
        raise ValueError("Dedicated running review database identity/port required")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPSPILOT_", "POSTGRES_", "LANGSMITH_", "LANGCHAIN_"))
        or k.startswith("OPSPILOT_AGENT_")
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
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args().arguments
    if args[:1] == ["--"]:
        args = args[1:]
    # The benchmark itself validates new output paths, scopes, splits and limits.
    if "--output" not in args or args.index("--output") + 1 >= len(args):
        parser.error("--output is required")
    output = (ROOT / args[args.index("--output") + 1]).resolve()
    if not output.is_relative_to(ROOT / "evaluations/reports") or output.exists():
        parser.error("Choose a new report inside evaluations/reports")
    log = output.with_suffix(".log")
    env = environment()
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run(
            [sys.executable, "-m", "evaluations.runners.benchmark", *args],
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    print(json.dumps({"benchmark_exit": result.returncode, "log": str(log.relative_to(ROOT))}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
