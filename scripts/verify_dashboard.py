"""Run real Chromium against an isolated PostgreSQL/MCP stack and production Next build."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wait_ready(process, predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while not predicate():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("Verification service unavailable; inspect Stage 6 logs")
        time.sleep(0.25)


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    if any(port_open(port) for port in [3001, 8087, 8088]):
        raise SystemExit("Stop the existing test stack first; no existing process will be replaced")
    ready = ROOT / "artifacts/stage6-browser-stack.ready"
    stop = ROOT / "artifacts/stage6-browser-stack.stop"
    ready.unlink(missing_ok=True)
    stop.unlink(missing_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "OPSPILOT_DASHBOARD_BACKEND_URL": "http://127.0.0.1:8087/",
            "OPSPILOT_DASHBOARD_SERVICE_KEY": "stage6-bff-test-key-" + "k" * 40,
            "NEXT_TELEMETRY_DISABLED": "1",
            "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "frontend/.cache/ms-playwright"),
        }
    )
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    processes = []
    with (
        (ROOT / "artifacts/stage6-browser-backend.log").open("w") as backend_log,
        (ROOT / "artifacts/stage6-next-test.log").open("w") as frontend_log,
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
            wait_ready(backend, ready.exists)
            print("Isolated PostgreSQL/MCP stack ready.", flush=True)
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
                stdout=frontend_log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(frontend)
            wait_ready(frontend, lambda: port_open(3001))
            result = subprocess.call(
                [node, "node_modules/@playwright/test/cli.js", "test"],
                cwd=ROOT / "frontend",
                env=env,
                creationflags=flags,
            )
            report_path = ROOT / "frontend/test-results/stage6-results.json"
            if report_path.exists():
                stats = json.loads(report_path.read_text(encoding="utf-8"))["stats"]
                print("Actual Chromium results: " + json.dumps(stats), flush=True)
            return result
        finally:
            stop.write_text("stop", encoding="utf-8")
            if processes:
                try:
                    processes[0].wait(timeout=45)
                except subprocess.TimeoutExpired:
                    # Only Popen handles created by this invocation are terminated.
                    processes[0].terminate()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)


if __name__ == "__main__":
    raise SystemExit(main())
