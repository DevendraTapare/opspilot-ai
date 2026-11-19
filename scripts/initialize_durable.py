"""Provision only local OpsPilot runner/operator roles and separate private files."""

import getpass
import hashlib
import json
import secrets
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.db import make_engine
from opspilot.gateway.contracts import TOOLS
from opspilot.schemas import ServiceName
from scripts.provision_gateway_db import main as provision_gateway

ROOT = Path(__file__).resolve().parents[1]


def write_values(path, values):
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main():
    values = dotenv_values(ROOT / ".env")
    url = make_url(values["OPSPILOT_DATABASE_URL"])
    if url.host != "127.0.0.1" or url.database != "opspilot":
        raise SystemExit("Provisioning is restricted to the dedicated local OpsPilot database")
    runner_path, operator_path = ROOT / ".runner.env", ROOT / ".operator.env"
    old_runner, old_operator = dotenv_values(runner_path), dotenv_values(operator_path)
    runner_password = (
        make_url(old_runner["OPSPILOT_DURABLE_DATABASE_URL"]).password
        if old_runner.get("OPSPILOT_DURABLE_DATABASE_URL")
        else secrets.token_hex(32)
    )
    operator_password = (
        make_url(old_operator["OPSPILOT_OPERATOR_DATABASE_URL"]).password
        if old_operator.get("OPSPILOT_OPERATOR_DATABASE_URL")
        else secrets.token_hex(32)
    )
    executor_token = old_runner.get("OPSPILOT_DURABLE_MCP_TOKEN") or secrets.token_hex(32)
    operator_token = old_operator.get("OPSPILOT_OPERATOR_TOKEN") or secrets.token_hex(32)
    operators = old_operator.get("OPSPILOT_OPERATOR_OPERATORS") or json.dumps(
        [
            {
                "subject": "local-human-operator",
                "os_user": getpass.getuser(),
                "token_sha256": hashlib.sha256(operator_token.encode()).hexdigest(),
                "services": list(ServiceName),
                "actions": [
                    "restart_simulated_worker",
                    "rollback_simulated_configuration",
                    "reset_simulated_dependency",
                ],
            }
        ]
    )
    engine = make_engine(values["OPSPILOT_DATABASE_URL"])
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT version_num FROM alembic_version")) not in {
                "0003_durable",
                "0004_dashboard",
            }:
                raise SystemExit("Apply Stage 4 migrations before provisioning roles")
        provision_gateway()
        with engine.begin() as connection:
            for role, password in [
                ("opspilot_runner", runner_password),
                ("opspilot_operator", operator_password),
            ]:
                # Identifiers are a fixed internal allowlist; secrets are bound, never printed.
                connection.execute(
                    text("SELECT set_config('opspilot.role_password', :p, true)"), {"p": password}
                )
                connection.execute(
                    text(f"""DO $$ BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
                      CONNECTION LIMIT 16;
                  END IF;
                  EXECUTE format('ALTER ROLE {role} PASSWORD %L',
                    current_setting('opspilot.role_password'));
                END $$""")
                )
                connection.execute(text(f"GRANT CONNECT ON DATABASE opspilot TO {role}"))
                connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
                connection.execute(
                    text(f"""GRANT SELECT ON services, faults, incidents,
                  incident_events, deployment_events, metric_summaries, simulation_logs,
                  action_approvals, action_executions, gateway_audit_events, durable_runs,
                  remediation_approvals, durable_attempts, remediation_verifications,
                  durable_audit_events, alembic_version TO {role}""")
                )
            connection.execute(
                text("""CREATE SCHEMA IF NOT EXISTS opspilot_checkpoints
                                      AUTHORIZATION opspilot_runner""")
            )
            connection.execute(
                text("""GRANT INSERT ON durable_runs, durable_attempts,
                                      durable_audit_events TO opspilot_runner""")
            )
            connection.execute(
                text("""GRANT INSERT (id, run_id, incident_id, tool, arguments,
                service_name, risk, evidence, preconditions, verification_plan, expires_at,
                fingerprint, created_at) ON remediation_approvals TO opspilot_runner""")
            )
            connection.execute(
                text("""GRANT UPDATE (status, action_result, verification, updated_at)
                                      ON durable_runs TO opspilot_runner""")
            )
            connection.execute(
                text("""GRANT UPDATE (outcome, finished_at) ON durable_attempts
                                      TO opspilot_runner""")
            )
            connection.execute(
                text("""GRANT INSERT ON action_approvals, durable_audit_events
                                      TO opspilot_operator""")
            )
            connection.execute(
                text("""GRANT UPDATE (state, approved_by, approved_at, revoked_by,
                revoked_at) ON remediation_approvals TO opspilot_operator""")
            )
            connection.execute(
                text("""GRANT SELECT ON durable_runs, remediation_approvals,
                durable_attempts, remediation_verifications, durable_audit_events
                TO opspilot_gateway""")
            )
            connection.execute(
                text("""GRANT UPDATE (state) ON remediation_approvals
                                      TO opspilot_gateway""")
            )
            connection.execute(
                text("""GRANT INSERT ON remediation_verifications, durable_audit_events,
                metric_summaries, simulation_logs, incidents, incident_events
                TO opspilot_gateway""")
            )
            connection.execute(
                text("""GRANT UPDATE (status, resolved_at) ON incidents
                                      TO opspilot_gateway""")
            )
            connection.execute(
                text("""GRANT USAGE ON SEQUENCE durable_audit_events_id_seq
                                      TO opspilot_runner, opspilot_operator, opspilot_gateway""")
            )
        callers = json.loads(values["OPSPILOT_GATEWAY_CALLERS"])
        policy = {
            "subject": "durable-executor",
            "token_sha256": hashlib.sha256(executor_token.encode()).hexdigest(),
            "services": list(ServiceName),
            "tools": list(TOOLS),
        }
        callers = [c for c in callers if c["subject"] != "durable-executor"] + [policy]
        lines = (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if not line.startswith("OPSPILOT_GATEWAY_CALLERS=")]
        lines.append("OPSPILOT_GATEWAY_CALLERS=" + json.dumps(callers, separators=(",", ":")))
        (ROOT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_values(
            runner_path,
            {
                "OPSPILOT_DURABLE_DATABASE_URL": url.set(
                    username="opspilot_runner", password=runner_password
                ).render_as_string(hide_password=False),
                "OPSPILOT_DURABLE_MCP_TOKEN": executor_token,
                "OPSPILOT_DURABLE_MCP_URL": "http://127.0.0.1:8085/mcp",
            },
        )
        write_values(
            operator_path,
            {
                "OPSPILOT_OPERATOR_DATABASE_URL": url.set(
                    username="opspilot_operator", password=operator_password
                ).render_as_string(hide_password=False),
                "OPSPILOT_OPERATOR_APPROVAL_KEY": values["OPSPILOT_GATEWAY_APPROVAL_KEY"],
                "OPSPILOT_OPERATOR_OPERATORS": operators,
                # Human retrieval only: the CLI never consumes this token automatically.
                "OPSPILOT_OPERATOR_TOKEN": operator_token,
            },
        )
        print("Provisioned local runner/operator/checkpoint permissions; action flag preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
