"""Bounded local jobs; durable actions retain Stage 4's independent ledger and locks."""

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.mcp import connect
from opspilot.agent.providers import HTTPDecisionModel
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from opspilot.durable.client import connect_executor
from opspilot.durable.persistence import PostgreSQLPersistence
from opspilot.durable.repository import Repository
from opspilot.durable.workflow import DurableExecution
from opspilot.models import DashboardRun, DurableRun, now


def real_model_available():
    try:
        HTTPDecisionModel.from_environment()
        return True
    except ValueError:
        return False


class Jobs:
    def __init__(self, engine, runner, settings, model_factory=None):
        self.engine, self.runner, self.settings = engine, runner, settings
        self.model_factory = model_factory
        self.tasks = {}
        self.semaphore = asyncio.Semaphore(1)

    def recover(self):
        with Session(self.engine) as session, session.begin():
            for row in session.scalars(
                select(DashboardRun).where(DashboardRun.status.in_(["queued", "running"]))
            ):
                # Never silently repeat paid inference after a process restart.
                row.status, row.error_code = "interrupted", "PROCESS_RESTARTED"
                row.updated_at = now()

    def enqueue(self, identity, budget=180, resume=False):
        if identity in self.tasks:
            return
        if len(self.tasks) >= 8:
            raise ValueError("QUEUE_FULL")
        task = asyncio.create_task(self.work(identity, budget, resume))
        self.tasks[identity] = task
        task.add_done_callback(lambda _: self.tasks.pop(identity, None))

    def save(self, identity, **updates):
        with Session(self.engine) as session, session.begin():
            row = session.get(DashboardRun, identity)
            if row:
                for key, value in updates.items():
                    setattr(row, key, value)
                row.updated_at = now()

    async def durable(self, identity, start):
        persistence = PostgreSQLPersistence(self.engine, self.runner.checkpoint_schema)
        async with (
            persistence.saver() as saver,
            connect_executor(self.runner.mcp_url, self.runner.mcp_token.get_secret_value()) as mcp,
        ):
            return await DurableExecution(self.engine, persistence, saver, mcp).drive(
                identity, start=start
            )

    async def work(self, identity, budget, resume):
        try:
            async with self.semaphore:
                if resume:
                    await self.durable(identity, False)
                    return
                with Session(self.engine) as session:
                    row = session.get(DashboardRun, identity)
                    request = RunRequest(
                        incident_id=row.incident_id,
                        service_name=row.service_name,
                        max_seconds=budget,
                    )
                    mode = row.mode
                self.save(identity, status="running")
                model = (
                    self.model_factory(mode, budget)
                    if self.model_factory
                    else FixtureDecisionModel()
                    if mode == "fixture"
                    else HTTPDecisionModel.from_environment()
                )
                async with connect(
                    self.runner.mcp_url, self.settings.reader_token.get_secret_value()
                ) as mcp:
                    result = await Investigation(
                        model,
                        mcp,
                        request,
                        run_id=UUID(identity),
                        progress_callback=lambda snapshot: self.save(identity, snapshot=snapshot),
                    ).run()
                snapshot = result.model_dump(mode="json")
                status = (
                    "timed_out" if result.run_status == "budget_exhausted" else result.run_status
                )
                self.save(identity, status=status, snapshot=snapshot)
                if (
                    result.run_status == "completed"
                    and result.proposed_remediation
                    and result.proposed_remediation.action != "manual_investigation"
                ):
                    Repository(self.engine).submit(snapshot, ttl=600)
                    await self.durable(identity, True)
        except asyncio.CancelledError:
            self.save(identity, status="interrupted", error_code="PROCESS_STOPPED")
            raise
        except Exception as exc:
            # Exception messages may contain provider URLs or diagnostic content.
            from opspilot.durable.contracts import ExecutionError

            code = exc.code if isinstance(exc, ExecutionError) else "DEPENDENCY_UNAVAILABLE"
            self.save(identity, status="failed", error_code=code)
            with Session(self.engine) as session:
                durable = session.get(DurableRun, identity)
            if durable:
                Repository(self.engine).event(identity, "dashboard_resume_failed", {"code": code})

    async def close(self):
        pending = list(self.tasks.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
