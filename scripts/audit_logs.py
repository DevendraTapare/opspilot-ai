"""Check application container logs for JSON structure and local secret leakage."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = subprocess.run(
        ["docker", "compose", "logs", "--no-color", "--no-log-prefix", "api", "traffic"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    secrets = [
        line.split("=", 1)[1]
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if line.startswith(("OPSPILOT_CONTROL_TOKEN=", "POSTGRES_PASSWORD="))
    ]
    contains_secrets = any(secret and secret in result.stdout for secret in secrets)
    rows = result.stdout.splitlines()
    valid_json = True
    for row in rows:
        try:
            json.loads(row)
        except json.JSONDecodeError:
            valid_json = False
    report = {
        "records_checked": len(rows),
        "all_records_are_json": valid_json,
        "contains_control_token_or_database_password": contains_secrets,
    }
    (ROOT / "artifacts" / "log-verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if not rows or contains_secrets or not valid_json:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
