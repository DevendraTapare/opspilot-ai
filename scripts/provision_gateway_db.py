"""Provision the fixed local PostgreSQL role used by the authorization service."""

import secrets
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.db import make_engine


def main():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(env_path)
    admin_url = values.get("OPSPILOT_DATABASE_URL", "")
    url = make_url(admin_url)
    if url.host != "127.0.0.1" or url.database != "opspilot":
        raise SystemExit("Provisioning is restricted to the dedicated local opspilot database")
    password = values.get("OPSPILOT_GATEWAY_DB_PASSWORD") or secrets.token_hex(32)
    engine = make_engine(admin_url)
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT version_num FROM alembic_version")) not in {
                "0002_gateway",
                "0003_durable",
                "0004_dashboard",
            }:
                raise SystemExit("Apply Stage 2 migrations before provisioning the gateway role")
            connection.execute(
                text("SELECT set_config('opspilot.gateway_password', :password, true)"),
                {"password": password},
            )
            connection.execute(
                text("""
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'opspilot_gateway') THEN
                    CREATE ROLE opspilot_gateway LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                      NOINHERIT CONNECTION LIMIT 24;
                  END IF;
                  EXECUTE format('ALTER ROLE opspilot_gateway PASSWORD %L',
                    current_setting('opspilot.gateway_password'));
                END $$
            """)
            )
            connection.execute(text("GRANT CONNECT ON DATABASE opspilot TO opspilot_gateway"))
            connection.execute(text("GRANT USAGE ON SCHEMA public TO opspilot_gateway"))
            connection.execute(
                text("""
                GRANT SELECT ON services, faults, incidents, incident_events, deployment_events,
                  metric_summaries, simulation_logs, action_approvals, action_executions,
                  gateway_audit_events, alembic_version TO opspilot_gateway
            """)
            )
            connection.execute(text("GRANT UPDATE (cursor) ON services TO opspilot_gateway"))
            connection.execute(
                text("GRANT UPDATE (active, deactivated_at) ON faults TO opspilot_gateway")
            )
            connection.execute(
                text("GRANT UPDATE (consumed_by) ON action_approvals TO opspilot_gateway")
            )
            connection.execute(
                text("""
                GRANT INSERT ON action_executions, deployment_events, gateway_audit_events
                TO opspilot_gateway
            """)
            )
            connection.execute(
                text("""
                GRANT UPDATE (outcome, service_name, approval_id, action_request_id)
                ON gateway_audit_events TO opspilot_gateway
            """)
            )
        gateway_url = url.set(username="opspilot_gateway", password=password).render_as_string(
            hide_password=False
        )
        changes = {
            "OPSPILOT_GATEWAY_DB_PASSWORD": password,
            "OPSPILOT_GATEWAY_DATABASE_URL": gateway_url,
        }
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if line.split("=", 1)[0] not in changes]
        lines.extend(f"{key}={value}" for key, value in changes.items())
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Provisioned fixed local gateway role; no grant-creation or deletion privilege.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
