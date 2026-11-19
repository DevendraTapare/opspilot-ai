"""Explicit durable start/resume/report commands; approval is a separate human CLI."""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from opspilot.db import make_engine
from opspilot.durable.client import connect_executor
from opspilot.durable.contracts import VerificationPlan
from opspilot.durable.persistence import PostgreSQLPersistence, run_async
from opspilot.durable.repository import Repository
from opspilot.durable.workflow import DurableExecution


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_DURABLE_", env_file=".runner.env", extra="ignore"
    )
    database_url: SecretStr
    mcp_token: SecretStr
    mcp_url: str = "http://127.0.0.1:8085/mcp"
    checkpoint_schema: str = "opspilot_checkpoints"


async def execute(args, settings, engine):
    repo = Repository(engine)
    if args.command == "start":
        raw = Path(args.investigation).read_bytes()
        if len(raw) > 262144:
            raise ValueError("investigation exceeds size limit")
        investigation = json.loads(raw)
        repo.submit(
            investigation,
            VerificationPlan(count=args.count, arrival_interval_ms=args.arrival_interval_ms),
            ttl=args.ttl,
            recovery_of=str(args.recovery_of) if args.recovery_of else None,
        )
        run_id = str(UUID(investigation["run_id"]))
    else:
        run_id = str(args.run_id)
    if args.command == "report":
        return repo.report(run_id)
    persistence = PostgreSQLPersistence(engine, settings.checkpoint_schema)
    async with (
        persistence.saver() as saver,
        connect_executor(settings.mcp_url, settings.mcp_token.get_secret_value()) as mcp,
    ):
        return await DurableExecution(engine, persistence, saver, mcp).drive(
            run_id, start=args.command == "start"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--investigation", required=True)
    start.add_argument("--count", type=int, default=12)
    start.add_argument("--arrival-interval-ms", type=int, default=25)
    start.add_argument("--ttl", type=int, default=300)
    start.add_argument("--recovery-of", type=UUID)
    for name in ["resume", "report"]:
        sub.add_parser(name).add_argument("--run-id", type=UUID, required=True)
    args = parser.parse_args()
    settings = RunnerSettings()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        result = run_async(execute(args, settings, engine))
        print(json.dumps(result, indent=2))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "rejected_or_unavailable",
                    "message": "Inspect the persisted run timeline; no approval was inferred.",
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
