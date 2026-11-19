"""Build/start only the release-check Compose project; retain its private volume."""

import json
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    private = ROOT / ".release-check.env"
    if not private.exists():
        with private.open("x", encoding="utf-8") as stream:
            stream.write("SMOKE_DB_PASSWORD=" + secrets.token_hex(32) + "\n")
            stream.write("SMOKE_CONTROL_TOKEN=" + secrets.token_hex(32) + "\n")
    values = dotenv_values(private)
    folder = (
        ROOT
        / "artifacts/stage8"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-docker-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True)
    command = [
        "docker",
        "compose",
        "--env-file",
        str(private),
        "-f",
        str(ROOT / "compose.release-check.yaml"),
    ]
    result = {"project": "opspilot-release-check", "passed": False, "volume_retained": True}
    print("Docker smoke evidence: " + str(folder.relative_to(ROOT)), flush=True)
    with (folder / "docker.log").open("w") as log:
        try:
            subprocess.run(
                command + ["up", "-d", "--build", "--wait"],
                cwd=ROOT,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
            )
            port = subprocess.run(
                command + ["port", "api", "8000"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            assert port.startswith("127.0.0.1:")
            with httpx2.Client(base_url="http://" + port, timeout=15, trust_env=False) as client:
                assert client.get("/health/ready").status_code == 200
                assert len(client.get("/api/v1/services").json()) == 3
                assert (
                    client.post(
                        "/api/v1/faults",
                        json={
                            "service_name": "checkout-service",
                            "scenario_id": "worker-saturation",
                        },
                    ).status_code
                    == 401
                )
                for service in ["checkout-service", "payment-service", "inventory-service"]:
                    response = client.post(
                        f"/api/v1/simulator/{service}/workloads",
                        headers={"Authorization": "Bearer " + values["SMOKE_CONTROL_TOKEN"]},
                        json={"count": 6, "arrival_interval_ms": 50},
                    )
                    assert response.status_code == 200
                    assert all(m["errors"] == 0 for m in response.json()["metrics"])
            result.update(
                passed=True,
                readiness=200,
                services=3,
                unauthorized_fault=401,
                healthy_workloads=3,
                api_binding=port,
            )
        finally:
            stopped = subprocess.run(
                command + ["stop"],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            result["shutdown_exit"] = stopped.returncode
            (folder / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    return int(not result["passed"] or result["shutdown_exit"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
