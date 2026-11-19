"""Trusted operator harness: prepare checkout only, then launch a credential-separated agent.

The trigger record is kept separately. No expected cause/fixture label is sent to the agent.
This harness is not a model tool and is never imported by the investigation workflow.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx2
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["fixture", "real"])
    parser.add_argument(
        "--prepare-checkout",
        action="store_true",
        required=True,
        help="Explicitly reset checkout fixtures and inject a checkout fault",
    )
    parser.add_argument("--output", default="artifacts/stage3-fixture-investigation.json")
    args = parser.parse_args()
    settings = dotenv_values(".env")
    ready = httpx2.get("http://127.0.0.1:8085/health/ready", trust_env=False, timeout=15)
    ready.raise_for_status()
    headers = {"Authorization": "Bearer " + settings["OPSPILOT_CONTROL_TOKEN"]}
    with httpx2.Client(
        base_url="http://127.0.0.1:8084", headers=headers, trust_env=False, timeout=30
    ) as api:

        def post(path, body):
            response = api.post(path, json=body)
            response.raise_for_status()
            return response.json()

        active = api.get("/api/v1/faults", params={"active": "true"})
        active.raise_for_status()
        if any(f["service_name"] != "checkout-service" for f in active.json()):
            raise SystemExit("A dependency has an active fault; leave it unchanged and stop.")
        post("/api/v1/fixtures/reset", {"services": ["checkout-service"], "seed": 42})
        post(
            "/api/v1/simulator/checkout-service/workloads", {"count": 12, "arrival_interval_ms": 25}
        )
        fault = post(
            "/api/v1/faults",
            {"service_name": "checkout-service", "scenario_id": "worker-saturation"},
        )
        workload = post(
            "/api/v1/simulator/checkout-service/workloads", {"count": 30, "arrival_interval_ms": 0}
        )
        incidents = api.get(
            "/api/v1/incidents", params={"service_name": "checkout-service", "status": "open"}
        )
        incidents.raise_for_status()
        incident_id = incidents.json()[0]["id"]
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".trigger.json").write_text(
            json.dumps(
                {
                    "operator_only": True,
                    "fault_id": fault["id"],
                    "scenario_id": fault["scenario_id"],
                    "incident_id": incident_id,
                    "run_id": workload["run_id"],
                    "reset_services": ["checkout-service"],
                    "seed": 42,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    # Do not inherit DB/admin/approval/operator secrets into the graph process.
    system_keys = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PATHEXT",
        "PYTHONPATH",
    }
    child_env = {key: value for key, value in os.environ.items() if key.upper() in system_keys}
    child_env.update(
        {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "OPSPILOT_AGENT_PROVIDER",
                "OPSPILOT_AGENT_MODEL",
                "OPSPILOT_AGENT_BASE_URL",
                "OPSPILOT_AGENT_API_KEY",
            }
        }
    )
    child_env["OPSPILOT_MCP_TOKEN"] = settings["OPSPILOT_MCP_READER_TOKEN"]
    child_env["LANGSMITH_TRACING"] = "false"
    child_env["LANGCHAIN_TRACING_V2"] = "false"
    start = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "opspilot.agent.cli",
            "--mode",
            args.mode,
            "--incident-id",
            incident_id,
            "--output",
            str(output),
        ],
        env=child_env,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    # The CLI handles failures without exposing provider exception bodies.
    print(result.stdout)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "exit_code": result.returncode,
                "process_latency_ms": round((time.monotonic() - start) * 1000, 2),
            }
        )
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
