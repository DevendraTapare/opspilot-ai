"""Preserved real-browser release evidence; only the dedicated local test database."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import URL

from scripts.verify_dashboard import port_open, wait_ready

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grep", help="Optional Playwright title filter for an isolated recheck")
    args = parser.parse_args()
    if any(port_open(p) for p in [3001, 8087, 8088]):
        raise SystemExit("Test ports occupied; existing processes will not be replaced")
    values = dotenv_values(ROOT / ".stage7.env")
    url = os.environ.get("OPSPILOT_TEST_DATABASE_URL") or URL.create(
        "postgresql+psycopg",
        username="opspilot_test",
        password=values["STAGE7_POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=int(values["STAGE7_DB_PORT"]),
        database="opspilot_stage1_test",
    ).render_as_string(hide_password=False)
    folder = (
        ROOT
        / "artifacts/stage8"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-browser-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPSPILOT_", "POSTGRES_", "LANGSMITH_", "LANGCHAIN_"))
    }
    env.update(
        OPSPILOT_BROWSER_TEST_DATABASE_URL=url,
        OPSPILOT_BROWSER_TEST_HUMAN=secrets.token_hex(32),
        OPSPILOT_BROWSER_TEST_KEY=secrets.token_hex(32),
        OPSPILOT_BROWSER_TEST_BASELINE="1",
        OPSPILOT_BROWSER_TEST_ARTIFACT_DIR=str(folder),
        OPSPILOT_BROWSER_TEST_OUTPUT=str(folder / "browser"),
        OPSPILOT_DASHBOARD_BACKEND_URL="http://127.0.0.1:8087/",
        NEXT_TELEMETRY_DISABLED="1",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    env["OPSPILOT_DASHBOARD_SERVICE_KEY"] = env["OPSPILOT_BROWSER_TEST_KEY"]
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "frontend/.cache/ms-playwright")
    )
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required")
    print("Release browser evidence: " + str(folder.relative_to(ROOT)), flush=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes = []
    with (
        (folder / "backend.log").open("w") as backend_log,
        (folder / "next.log").open("w") as next_log,
    ):
        try:
            backend = subprocess.Popen(
                [sys.executable, "-m", "scripts.serve_dashboard_test"],
                cwd=ROOT,
                env=env,
                stdout=backend_log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(backend)
            wait_ready(backend, (folder / "stage6-browser-stack.ready").exists)
            frontend = subprocess.Popen(
                [
                    node,
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3001",
                ],
                cwd=ROOT / "frontend",
                env=env,
                stdout=next_log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(frontend)
            wait_ready(frontend, lambda: port_open(3001))
            with (folder / "playwright.log").open("w") as log:
                result = subprocess.run(
                    [node, "node_modules/@playwright/test/cli.js", "test"]
                    + (["--grep", args.grep] if args.grep else []),
                    cwd=ROOT / "frontend",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                    check=False,
                )
            report = folder / "browser/stage6-results.json"
            if report.exists():
                print(json.dumps(json.loads(report.read_text())["stats"]), flush=True)
            return result.returncode
        finally:
            (folder / "stage6-browser-stack.stop").write_text("stop")
            if processes:
                try:
                    processes[0].wait(timeout=45)
                except subprocess.TimeoutExpired:
                    processes[0].terminate()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)


if __name__ == "__main__":
    raise SystemExit(main())
