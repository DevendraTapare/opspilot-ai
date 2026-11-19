"""Loopback dashboard API entry point. No tokens are passed on the command line."""

import uvicorn

from opspilot.dashboard.api import create_dashboard
from opspilot.dashboard.config import DashboardSettings
from opspilot.db import make_engine
from opspilot.durable.cli import RunnerSettings
from opspilot.durable.operator import OperatorSettings
from opspilot.durable.persistence import run_async
from opspilot.logging import configure_logging


def main():
    settings, runner, operator = DashboardSettings(), RunnerSettings(), OperatorSettings()
    engine = make_engine(runner.database_url.get_secret_value())
    operator_engine = make_engine(operator.database_url.get_secret_value())
    configure_logging("INFO")
    try:
        app = create_dashboard(settings, runner, operator, engine, operator_engine)
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=8086, access_log=False, log_config=None, ws="none"
            )
        )
        run_async(server.serve())
    finally:
        engine.dispose()
        operator_engine.dispose()


if __name__ == "__main__":
    main()
