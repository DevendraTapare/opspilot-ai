"""Inspect actual local container/DB boundaries without printing credentials or raw logs."""

import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.db import make_engine

ROOT = Path(__file__).resolve().parents[1]


def docker(*arguments):
    return subprocess.run(
        ["docker", *arguments], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout


def main():
    env = dotenv_values(ROOT / ".env")
    report = {}
    engine = make_engine(env["OPSPILOT_GATEWAY_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            report["database_role"] = connection.scalar(text("SELECT current_user"))
            for key, query in {
                "can_insert_approvals": (
                    "SELECT has_table_privilege(current_user, 'action_approvals', 'INSERT')"
                ),
                "can_edit_approval_signature": (
                    "SELECT has_column_privilege(current_user, "
                    "'action_approvals', 'signature', 'UPDATE')"
                ),
                "can_delete_faults": "SELECT has_table_privilege(current_user, 'faults', 'DELETE')",
                "can_create_in_public_schema": (
                    "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
                ),
            }.items():
                report[key] = connection.scalar(text(query))
                assert report[key] is False
            report["runtime_approvals"] = connection.scalar(
                text("SELECT count(*) FROM action_approvals")
            )
            report["runtime_action_executions"] = connection.scalar(
                text("SELECT count(*) FROM action_executions")
            )
            report["persisted_gateway_audit_events"] = connection.scalar(
                text("SELECT count(*) FROM gateway_audit_events")
            )
            assert report["runtime_approvals"] == report["runtime_action_executions"] == 0
    finally:
        engine.dispose()
    for service in ("mcp", "authorizer"):
        container_id = docker("compose", "ps", "-q", service).strip()
        config = json.loads(docker("inspect", container_id))[0]
        variables = dict(item.split("=", 1) for item in config["Config"]["Env"] if "=" in item)
        assert "OPSPILOT_CONTROL_TOKEN" not in variables
        assert "OPSPILOT_MCP_OPERATOR_TOKEN" not in variables
        assert config["HostConfig"]["ReadonlyRootfs"]
        assert config["Config"]["User"] == "opspilot"
        assert not any(mount["Type"] == "bind" for mount in config["Mounts"])
        if service == "mcp":
            names = {name for name in variables if name.startswith("OPSPILOT_")}
            assert names == {
                "OPSPILOT_GATEWAY_CALLERS",
                "OPSPILOT_GATEWAY_DELEGATION_KEY",
                "OPSPILOT_GATEWAY_BACKEND_URL",
            }
            report["mcp_has_no_db_approval_or_admin_credentials"] = True
        else:
            assert (
                make_url(variables["OPSPILOT_GATEWAY_DATABASE_URL"]).username == "opspilot_gateway"
            )
            assert variables["OPSPILOT_GATEWAY_ACTIONS_ENABLED"] == "false"
            report["runtime_actions_disabled"] = True
    logs = docker("compose", "logs", "--no-color", "--no-log-prefix", "mcp", "authorizer")
    rows = [json.loads(row) for row in logs.splitlines() if row.strip()]
    secrets = [
        value
        for key, value in env.items()
        if value and key.endswith(("_TOKEN", "_PASSWORD", "_KEY"))
    ]
    assert not any(secret in logs for secret in secrets)
    report["json_log_records_checked"] = len(rows)
    report["contains_generated_secrets"] = False
    report["container_filesystems_readonly_no_host_binds"] = True
    (ROOT / "artifacts" / "stage2-security-verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
