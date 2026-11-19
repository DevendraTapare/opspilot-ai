"""Subprocess crash fixture, hard-restricted to the isolated test database/schema."""

import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from opspilot.durable.client import connect_executor
from opspilot.durable.persistence import PostgreSQLPersistence, run_async
from opspilot.durable.workflow import DurableExecution


async def main():
    url = make_url(os.environ["OPSPILOT_CRASH_TEST_DATABASE_URL"])
    schema = os.environ["OPSPILOT_CRASH_TEST_SCHEMA"]
    if (
        url.database != "opspilot_stage1_test"
        or url.host not in {"127.0.0.1", "test-db"}
        or not re.fullmatch(r"opspilot_test_[0-9a-f]{32}", schema)
    ):
        raise RuntimeError("Crash injection is restricted to a fresh isolated test schema")
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True
    )
    persistence = PostgreSQLPersistence(engine, schema)
    point = os.environ["OPSPILOT_CRASH_TEST_POINT"]

    def crash(where):
        if where == point:
            # Hard process exit: no Python finally blocks, no graceful saver/lock cleanup.
            os._exit(91)

    try:
        async with (
            persistence.saver() as saver,
            connect_executor(
                os.environ["OPSPILOT_CRASH_TEST_MCP_URL"], os.environ["OPSPILOT_CRASH_TEST_TOKEN"]
            ) as mcp,
        ):
            report = await DurableExecution(engine, persistence, saver, mcp, crash).drive(
                os.environ["OPSPILOT_CRASH_TEST_RUN_ID"], start=point == "before_approval_restart"
            )
            if point == "before_approval_restart":
                os._exit(91)
        Path(os.environ["OPSPILOT_CRASH_TEST_OUTPUT"]).write_text(
            json.dumps(report), encoding="utf-8"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    run_async(main())
