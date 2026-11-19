"""Verify real HTTP effects and persistence across an operator-requested stack restart.

Run from repository root with the dev environment: python -m scripts.verify_stack.
This intentionally resets the three named local fictional fixtures; never target a
different API. Generated evidence excludes tokens and database credentials.
"""

import argparse
import json
import time
from pathlib import Path

import httpx2

from opspilot.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "http-verification.json"
SERVICES = ["checkout-service", "payment-service", "inventory-service"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after-restart", action="store_true")
    arguments = parser.parse_args()
    settings = get_settings()
    with httpx2.Client(
        base_url="http://127.0.0.1:8084",
        headers={"Authorization": f"Bearer {settings.control_token.get_secret_value()}"},
        timeout=20,
    ) as client:
        client.get("/health/ready").raise_for_status()

        def reset():
            response = client.post(
                "/api/v1/fixtures/reset", json={"services": SERVICES, "seed": 42}
            )
            response.raise_for_status()

        if arguments.after_restart:
            evidence = json.loads(ARTIFACT.read_text(encoding="utf-8"))
            for row in evidence["scenarios"]:
                for incident_id in row["incident_ids"]:
                    incident = client.get(f"/api/v1/incidents/{incident_id}")
                    incident.raise_for_status()
                    assert incident.json()["events"]
                    assert client.get(f"/api/v1/incidents/{incident_id}/metrics").json()
                    assert client.get(f"/api/v1/incidents/{incident_id}/logs").json()
            assert not client.get("/api/v1/faults?active=true").json()
            evidence["persistence_after_db_and_api_restart"] = "passed"
            ARTIFACT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(
                "Persistence verified: incidents, events, metrics, logs, and reset state survived."
            )
            return

        rows = []
        cases = [
            ("healthy-baseline", "checkout-service", None, 1, 200),
            ("slow-checkout", "checkout-service", "slow-checkout", 1, 200),
            ("payment-unavailable", "payment-service", "payment-unavailable", 1, 503),
            ("inventory-db-exhaustion", "inventory-service", "inventory-db-exhaustion", 1, 503),
            ("worker-saturation", "payment-service", "worker-saturation", 30, 200),
            ("bad-config", "checkout-service", "bad-config", 1, 500),
        ]
        try:
            for label, service, scenario, count, expected_status in cases:
                reset()
                if scenario:
                    client.post(
                        "/api/v1/faults",
                        json={
                            "service_name": service,
                            "scenario_id": scenario,
                        },
                    ).raise_for_status()
                started = time.perf_counter()
                if count == 1:
                    response = client.post(f"/api/v1/simulator/{service}/request")
                else:
                    response = client.post(
                        f"/api/v1/simulator/{service}/workloads",
                        json={
                            "count": count,
                            "arrival_interval_ms": 0,
                        },
                    )
                elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                assert response.status_code == expected_status, response.text
                run = response.json()
                metric = next(m for m in run["metrics"] if m["service_name"] == service)
                if scenario == "slow-checkout":
                    assert elapsed_ms >= 550 and metric["p95_latency_ms"] >= 550
                if scenario == "worker-saturation":
                    assert metric["errors"] > 0 and metric["worker_utilization"] > 0.8
                if scenario == "inventory-db-exhaustion":
                    assert metric["db_pool_utilization"] == 1
                incidents = client.get("/api/v1/incidents?status=open").json()
                rows.append(
                    {
                        "scenario": label,
                        "service": service,
                        "http_status": response.status_code,
                        "wall_duration_ms": elapsed_ms,
                        "requests": metric["requests"],
                        "errors": metric["errors"],
                        "p95_latency_ms": metric["p95_latency_ms"],
                        "worker_utilization": metric["worker_utilization"],
                        "db_pool_utilization": metric["db_pool_utilization"],
                        "incident_ids": [incident["id"] for incident in incidents],
                    }
                )
        finally:
            reset()
        evidence = {"scenarios": rows, "persistence_after_db_and_api_restart": "not run"}
        ARTIFACT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
