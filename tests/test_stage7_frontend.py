"""Actual Next production HTTP boundary; synthetic configuration, no main API."""

import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx2
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def next_review_server(tmp_path_factory):
    node = shutil.which("node")
    if not node or not (ROOT / "frontend/.next/BUILD_ID").exists():
        pytest.skip("Build the production frontend to exercise its actual HTTP boundary")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 3007))
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "COMSPEC"}
    }
    env.update(
        OPSPILOT_DASHBOARD_BACKEND_URL="http://127.0.0.1:39999/",
        OPSPILOT_DASHBOARD_SERVICE_KEY="STAGE7_SERVER_ONLY_CANARY_" + "k" * 40,
        NEXT_TELEMETRY_DISABLED="1",
    )
    log = tmp_path_factory.mktemp("next-review") / "server.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                node,
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                "3007",
            ],
            cwd=ROOT / "frontend",
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 40
            while True:
                try:
                    if httpx2.get("http://127.0.0.1:3007/", timeout=2).status_code == 200:
                        break
                except httpx2.HTTPError:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    pytest.fail("Isolated production Next server did not start")
                time.sleep(0.1)
            yield "http://127.0.0.1:3007"
        finally:
            process.terminate()
            process.wait(timeout=15)


def test_next_slow_body_is_closed_by_deadline(next_review_server, record_property):
    with socket.create_connection(("127.0.0.1", 3007), timeout=10) as stream:
        stream.sendall(
            b"POST /api/ops/session HTTP/1.1\r\nHost: 127.0.0.1:3007\r\n"
            b"Origin: http://127.0.0.1:3007\r\nContent-Type: application/json\r\n"
            b"Content-Length: 100\r\nConnection: close\r\n\r\n{"
        )
        response = stream.recv(4096)
    assert b"408" in response.split(b"\r\n")[0]
    record_property("actual", "Actual Next TCP request returned HTTP 408 for an unfinished body")


@pytest.mark.parametrize(
    "attack,expected",
    [("unknown_tool", 404), ("csrf", 403), ("oversize", 413), ("backend_outage", 503)],
)
def test_next_rejects_unsafe_requests(next_review_server, attack, expected, record_property):
    path = "/api/ops/session" if attack != "unknown_tool" else "/api/ops/tools/execute_shell"
    headers = {"Origin": next_review_server, "Content-Type": "application/json"}
    if attack == "csrf":
        headers["Origin"] = "https://attacker.invalid"
    body = "x" * 17000 if attack == "oversize" else "{}"
    response = httpx2.post(next_review_server + path, content=body, headers=headers, timeout=15)
    assert response.status_code == expected
    assert "STAGE7_SERVER_ONLY_CANARY" not in response.text
    record_property(
        "actual", f"Actual Next HTTP status {response.status_code}; no canary disclosure"
    )


def test_browser_assets_do_not_contain_backend_credential(next_review_server, record_property):
    html = httpx2.get(next_review_server, timeout=10).text
    paths = set(re.findall(r'(/_next/static/[^"<> ]+\.js)', html))
    assert paths
    for path in paths:
        data = httpx2.get(next_review_server + path, timeout=10).text
        assert "STAGE7_SERVER_ONLY_CANARY" not in data
    record_property(
        "actual", f"Inspected {len(paths)} actual browser JS assets; server canary absent"
    )
