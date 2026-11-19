"""Dedicated review subprocess; no shutdown hook is added to the runtime API."""

import asyncio
import os
import re
from pathlib import Path

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.durable.persistence import run_async
from opspilot.main import create_app


async def main():
    url = make_url(os.environ["OPSPILOT_REVIEW_DATABASE_URL"])
    schema = os.environ["OPSPILOT_REVIEW_SCHEMA"]
    signal = Path(os.environ["OPSPILOT_REVIEW_STOP"]).resolve()
    root = Path(__file__).resolve().parents[1]
    if (
        url.host != "127.0.0.1"
        or url.database != "opspilot_stage1_test"
        or not re.fullmatch(r"opspilot_test_[0-9a-f]{32}", schema)
        or not signal.is_relative_to(root / "artifacts")
    ):
        raise ValueError("review subprocess is restricted to its test database/schema")
    engine = create_engine(
        url,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-csearch_path=" + schema},
    )
    settings = Settings(control_token=os.environ["OPSPILOT_REVIEW_CONTROL"], _env_file=None)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, engine),
            host="127.0.0.1",
            port=int(os.environ["OPSPILOT_REVIEW_PORT"]),
            access_log=False,
            log_config=None,
            timeout_graceful_shutdown=3,
            ws="none",
        )
    )

    async def stop_when_requested():
        while not signal.exists():
            await asyncio.sleep(0.1)
        server.should_exit = True

    try:
        await asyncio.gather(server.serve(), stop_when_requested())
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        run_async(main())
    except Exception:
        print("Isolated simulator worker unavailable.")
        raise SystemExit(2) from None
