"""Provision local UI files and narrow Stage 6 table permissions; never enables actions."""

import secrets
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from scripts.initialize_durable import main as initialize_durable
from scripts.initialize_durable import write_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    initialize_durable()
    values = dotenv_values(ROOT / ".env")
    engine = create_engine(
        values["OPSPILOT_DATABASE_URL"],
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    try:
        with engine.begin() as connection:
            if (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                != "0004_dashboard"
            ):
                raise SystemExit("Apply Stage 6 migrations first")
            connection.execute(
                text("GRANT SELECT, INSERT, UPDATE ON dashboard_runs TO opspilot_runner")
            )
            connection.execute(
                text("GRANT SELECT, INSERT, UPDATE ON dashboard_sessions TO opspilot_operator")
            )
    finally:
        engine.dispose()
    private = dotenv_values(ROOT / ".dashboard.env")
    key = private.get("OPSPILOT_DASHBOARD_SERVICE_KEY") or secrets.token_hex(32)
    # Reader identity is selected from existing configuration; no new unscoped MCP caller.
    reader = values.get("OPSPILOT_MCP_READER_TOKEN")
    if not reader:
        raise SystemExit("Initialize the Stage 2 reader token first")
    write_values(
        ROOT / ".dashboard.env",
        {
            "OPSPILOT_DASHBOARD_SERVICE_KEY": key,
            "OPSPILOT_DASHBOARD_READER_TOKEN": reader,
            "OPSPILOT_DASHBOARD_CONTROL_TOKEN": values["OPSPILOT_CONTROL_TOKEN"],
            "OPSPILOT_DASHBOARD_ORIGIN": "http://127.0.0.1:3000",
            "OPSPILOT_DASHBOARD_ACTIONS_ENABLED": values.get(
                "OPSPILOT_GATEWAY_ACTIONS_ENABLED", "false"
            ),
        },
    )
    write_values(
        ROOT / "frontend/.env.local",
        {
            "OPSPILOT_DASHBOARD_BACKEND_URL": "http://127.0.0.1:8086/",
            "OPSPILOT_DASHBOARD_SERVICE_KEY": key,
        },
    )
    print("Provisioned local dashboard. Server credentials remain in ignored private files.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Dashboard provisioning unavailable. Verify local database readiness.")
        raise SystemExit(2) from None
