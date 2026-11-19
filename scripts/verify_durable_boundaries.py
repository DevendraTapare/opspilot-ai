"""Read-only verification of actual local runner/operator/backend privileges."""

import json
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.db import make_engine

ROOT = Path(__file__).resolve().parents[1]


def main():
    runner = dotenv_values(ROOT / ".runner.env")
    operator = dotenv_values(ROOT / ".operator.env")
    app = dotenv_values(ROOT / ".env")
    checks = {
        "runner": (
            runner["OPSPILOT_DURABLE_DATABASE_URL"],
            {
                "can_insert_grants": (
                    "SELECT has_table_privilege(current_user,'action_approvals','INSERT')",
                    False,
                ),
                "can_approve": (
                    "SELECT has_column_privilege(current_user,"
                    "'remediation_approvals','state','UPDATE')",
                    False,
                ),
                "can_insert_approver": (
                    "SELECT has_column_privilege(current_user,"
                    "'remediation_approvals','approved_by','INSERT')",
                    False,
                ),
                "can_change_fault": (
                    "SELECT has_table_privilege(current_user,'faults','UPDATE')",
                    False,
                ),
                "can_delete_audit": (
                    "SELECT has_table_privilege(current_user,'durable_audit_events','DELETE')",
                    False,
                ),
                "owns_checkpoint_schema": (
                    "SELECT has_schema_privilege(current_user,'opspilot_checkpoints','CREATE')",
                    True,
                ),
            },
        ),
        "operator": (
            operator["OPSPILOT_OPERATOR_DATABASE_URL"],
            {
                "can_insert_grants": (
                    "SELECT has_table_privilege(current_user,'action_approvals','INSERT')",
                    True,
                ),
                "can_approve": (
                    "SELECT has_column_privilege(current_user,"
                    "'remediation_approvals','state','UPDATE')",
                    True,
                ),
                "can_change_fault": (
                    "SELECT has_table_privilege(current_user,'faults','UPDATE')",
                    False,
                ),
                "can_forge_execution": (
                    "SELECT has_table_privilege(current_user,'action_executions','INSERT')",
                    False,
                ),
            },
        ),
        "backend": (
            app["OPSPILOT_GATEWAY_DATABASE_URL"],
            {
                "can_insert_grants": (
                    "SELECT has_table_privilege(current_user,'action_approvals','INSERT')",
                    False,
                ),
                "can_change_approver": (
                    "SELECT has_column_privilege(current_user,"
                    "'remediation_approvals','approved_by','UPDATE')",
                    False,
                ),
                "can_record_verification": (
                    "SELECT has_table_privilege(current_user,'remediation_verifications','INSERT')",
                    True,
                ),
            },
        ),
    }
    report = {}
    for name, (raw_url, expected) in checks.items():
        url = make_url(raw_url)
        if url.host != "127.0.0.1" or url.database != "opspilot":
            raise RuntimeError("Only local OpsPilot credentials may be inspected")
        engine = make_engine(raw_url)
        try:
            with engine.connect() as connection:
                result = {"database_role": connection.scalar(text("SELECT current_user"))}
                for label, (query, value) in expected.items():
                    result[label] = connection.scalar(text(query))
                    assert result[label] is value, label
                report[name] = result
        finally:
            engine.dispose()
    assert "APPROVAL_KEY" not in " ".join(runner)
    assert "OPSPILOT_OPERATOR_TOKEN" not in runner
    report["worker_private_config_has_no_approval_key_or_operator_token"] = True
    (ROOT / "artifacts/stage4-runtime-boundaries.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
