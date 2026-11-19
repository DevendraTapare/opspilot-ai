"""Stage 4: actual PostgreSQL checkpoints, MCP calls, synthetic authenticated humans.

TTY/input mocks represent test humans only. They are never runtime approval mechanisms.
"""

import asyncio
import getpass
import hashlib
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_mcp import serve

from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.mcp import connect
from opspilot.agent.providers import ModelReply
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from opspilot.durable.client import connect_executor
from opspilot.durable.contracts import ExecutionError, VerificationPlan
from opspilot.durable.operator import authenticate_operator, decide_interactively
from opspilot.durable.persistence import PostgreSQLPersistence
from opspilot.durable.repository import Repository
from opspilot.durable.workflow import DurableExecution
from opspilot.gateway.authorizer import create_authorizer
from opspilot.gateway.contracts import READ_TOOLS, TOOLS, GatewayError
from opspilot.gateway.mcp_server import create_mcp_app
from opspilot.gateway.security import AuthorizerSettings, GatewaySettings
from opspilot.models import (
    ActionApproval,
    ActionExecution,
    DurableAttempt,
    Fault,
    RemediationVerification,
)
from opspilot.schemas import ServiceName

READER_TOKEN = "stage4-test-reader-" + "r" * 40
EXECUTOR_TOKEN = "stage4-test-executor-" + "e" * 40
HUMAN_TOKEN = "stage4-synthetic-human-" + "h" * 40
REGISTRY = json.dumps(
    [
        {
            "subject": "synthetic-test-human",
            "os_user": getpass.getuser(),
            "token_sha256": hashlib.sha256(HUMAN_TOKEN.encode()).hexdigest(),
            "services": list(ServiceName),
            "actions": [
                "restart_simulated_worker",
                "rollback_simulated_configuration",
                "reset_simulated_dependency",
            ],
        }
    ]
)
POLICIES = json.dumps(
    [
        {
            "subject": subject,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "services": list(ServiceName),
            "tools": list(tools),
        }
        for subject, token, tools in [
            ("incident-reader", READER_TOKEN, READ_TOOLS),
            ("durable-executor", EXECUTOR_TOKEN, TOOLS),
        ]
    ]
)


@pytest.fixture
def anyio_backend():
    return (
        ("asyncio", {"loop_factory": asyncio.SelectorEventLoop})
        if sys.platform == "win32"
        else "asyncio"
    )


@pytest.fixture
def durable_engine(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip(
            "Stage 4 durability guarantees require real PostgreSQL, never a memory fallback"
        )
    return engine


@pytest.fixture
def durable_stack(durable_engine):
    settings = AuthorizerSettings(
        callers=POLICIES,
        delegation_key="stage4-delegation-" + "d" * 40,
        approval_key="stage4-signing-" + "s" * 40,
        actions_enabled=True,
        database_url=durable_engine.url.render_as_string(hide_password=False),
        requests_per_minute=600,
        actions_per_minute=60,
        _env_file=None,
    )
    with ExitStack() as stack:
        backend = stack.enter_context(serve(create_authorizer(settings, durable_engine)))
        gateway = stack.enter_context(
            serve(
                create_mcp_app(
                    GatewaySettings(
                        callers=POLICIES,
                        delegation_key=settings.delegation_key,
                        backend_url=backend,
                        timeout_seconds=10,
                        requests_per_minute=600,
                        actions_per_minute=60,
                        _env_file=None,
                    )
                )
            )
        )
        yield gateway + "/mcp", settings


@pytest.fixture
def persistence(durable_engine):
    with durable_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    return PostgreSQLPersistence(durable_engine, checkpoint_schema=schema)


@pytest.fixture
async def prepared(durable_stack, client, activate, workload):
    workload("checkout-service")
    fault = activate("checkout-service", "worker-saturation")
    workload("checkout-service", count=30, interval=0)
    incident = client.get("/api/v1/incidents?service_name=checkout-service&status=open").json()[0]
    async with connect(durable_stack[0], READER_TOKEN) as mcp:
        investigation = await Investigation(
            FixtureDecisionModel(),
            mcp,
            RunRequest(incident_id=incident["id"], service_name="checkout-service"),
        ).run()
    assert investigation.run_status == "completed", investigation.errors
    return investigation, fault


def approve(engine, settings, approval_id, monkeypatch, decision="approve", token=HUMAN_TOKEN):
    request = Repository(engine).request_by_id(approval_id)
    with monkeypatch.context() as patch:
        patch.setattr(sys.stdin, "isatty", lambda: True)
        patch.setattr(sys.stdout, "isatty", lambda: True)
        patch.setattr(getpass, "getpass", lambda _: token)
        patch.setattr("builtins.input", lambda _: f"{decision.upper()} {request.fingerprint}")
        return decide_interactively(engine, settings, REGISTRY, approval_id, decision)


def counts(engine):
    with Session(engine) as session:
        return {
            "effects": session.scalar(select(func.count()).select_from(ActionExecution)),
            "verifications": session.scalar(
                select(func.count()).select_from(RemediationVerification)
            ),
            "grants": session.scalar(select(func.count()).select_from(ActionApproval)),
        }


async def start_run(engine, persistence, mcp, investigation, recovery_of=None):
    repo = Repository(engine)
    approval_id = repo.submit(investigation, VerificationPlan(), recovery_of=recovery_of)
    run_id = str(investigation.run_id)
    async with persistence.saver() as saver:
        execution = DurableExecution(engine, persistence, saver, mcp)
        report = await execution.drive(run_id, start=True)
        snapshot = await execution.graph.aget_state({"configurable": {"thread_id": run_id}})
        assert snapshot.next == ("await_approval",)
        assert any(t.interrupts for t in snapshot.tasks)
    assert report["status"] == "awaiting_approval"
    return run_id, approval_id


@pytest.mark.anyio
async def test_restart_before_approval_and_real_mcp_verification(
    durable_engine, persistence, durable_stack, prepared, monkeypatch
):
    investigation, fault = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        with pytest.raises(GatewayError):
            async with persistence.saver() as saver:
                await DurableExecution(durable_engine, persistence, saver, mcp).drive(run_id)
        request = Repository(durable_engine).request(run_id)
        denied = await mcp.call(request.tool, request.arguments)
        assert denied["ok"] is False
        assert counts(durable_engine)["effects"] == 0
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        # New saver/graph instances read the durable interrupt, not in-memory state.
        async with persistence.saver() as saver:
            report = await DurableExecution(durable_engine, persistence, saver, mcp).drive(run_id)
        assert report["status"] == "verified", report
        assert report["verification"]["outcome"] == "verified"
        assert report["verification"]["metrics"][0]["error_rate"] == 0
        assert counts(durable_engine) == {"effects": 1, "verifications": 1, "grants": 1}
        with Session(durable_engine) as session:
            assert session.get(Fault, fault["id"]).active is False
        with pytest.raises(ExecutionError, match="RUN_TERMINAL"):
            async with persistence.saver() as saver:
                await DurableExecution(durable_engine, persistence, saver, mcp).drive(run_id)


class SimulatedCrash(BaseException):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    "point",
    [
        "after_approval",
        "before_tool_execution",
        "after_tool_before_acknowledgment",
        "after_verification_before_acknowledgment",
    ],
)
async def test_crash_boundaries_reconcile_without_repeating_effect(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, point
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)

        def crash(where):
            if where == point:
                raise SimulatedCrash(point)

        async with persistence.saver() as saver:
            with pytest.raises(SimulatedCrash):
                await DurableExecution(durable_engine, persistence, saver, mcp, crash).drive(run_id)
        before = counts(durable_engine)
        assert before["effects"] == int(
            point
            in {"after_tool_before_acknowledgment", "after_verification_before_acknowledgment"}
        )
        async with persistence.saver() as saver:
            report = await DurableExecution(durable_engine, persistence, saver, mcp).drive(run_id)
        assert report["status"] == "verified", report
        assert counts(durable_engine)["effects"] == counts(durable_engine)["verifications"] == 1
        assert report["approval"]["state"] == "consumed"


@pytest.mark.anyio
async def test_duplicate_submission_and_human_decision(
    durable_engine, persistence, durable_stack, prepared, monkeypatch
):
    investigation, _ = prepared
    repo = Repository(durable_engine)
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        assert repo.submit(investigation, VerificationPlan()) == approval_id
        changed = investigation.model_copy(deep=True)
        changed.goal = "A different investigation"
        with pytest.raises(ExecutionError, match="RUN_INPUT_MISMATCH"):
            repo.submit(changed, VerificationPlan())
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        with pytest.raises(ExecutionError, match="ALREADY_DECIDED"):
            approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        assert counts(durable_engine)["grants"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", ["expired", "revoked", "stale"])
async def test_expired_revoked_and_stale_approval(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, client, auth, invalid
):
    investigation, fault = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        if invalid == "expired":

            class Later(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.now(UTC) + timedelta(minutes=11)

            monkeypatch.setattr("opspilot.durable.policy.datetime", Later)
        elif invalid == "revoked":
            approve(durable_engine, durable_stack[1], approval_id, monkeypatch, "revoke")
        else:
            assert (
                client.post(f"/api/v1/faults/{fault['id']}/deactivate", headers=auth).status_code
                == 200
            )
        request = Repository(durable_engine).request(run_id)
        result = await mcp.call(request.tool, request.arguments)
        assert not result["ok"]
        expected = {
            "expired": "APPROVAL_EXPIRED",
            "revoked": "APPROVAL_REVOKED",
            "stale": "STALE_APPROVAL",
        }[invalid]
        assert result["error"]["code"] == expected, result
        with pytest.raises(GatewayError):
            async with persistence.saver() as saver:
                await DurableExecution(durable_engine, persistence, saver, mcp).drive(run_id)
        assert counts(durable_engine)["effects"] == 0


@pytest.mark.anyio
async def test_concurrent_resume_is_excluded(
    durable_engine, persistence, durable_stack, prepared, monkeypatch
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        entered, release = asyncio.Event(), asyncio.Event()

        class PauseBeforeAction:
            async def call(self, name, arguments):
                if name == "restart_simulated_worker":
                    entered.set()
                    await release.wait()
                return await mcp.call(name, arguments)

        async with persistence.saver() as first, persistence.saver() as second:
            first_task = asyncio.create_task(
                DurableExecution(durable_engine, persistence, first, PauseBeforeAction()).drive(
                    run_id
                )
            )
            await asyncio.wait_for(entered.wait(), 20)
            try:
                with pytest.raises(ExecutionError, match="RUN_BUSY"):
                    await DurableExecution(durable_engine, persistence, second, mcp).drive(run_id)
            finally:
                release.set()
            report = await first_task
        assert report["status"] == "verified"
        assert counts(durable_engine)["effects"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["request_id", "run_id", "service_name", "tool"])
async def test_approval_cannot_authorize_changed_arguments_or_run(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, change
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
        request = Repository(durable_engine).request(run_id)
        args = dict(request.arguments)
        tool = request.tool
        if change == "service_name":
            args[change] = "payment-service"
        elif change == "tool":
            tool = "rollback_simulated_configuration"
        else:
            args[change] = str(uuid4())
        response = await mcp.call(tool, args)
        assert not response["ok"] and response["error"]["code"] == "APPROVAL_INVALID"
        assert counts(durable_engine)["effects"] == 0


@pytest.mark.anyio
async def test_action_success_but_verification_failure_requires_separate_recovery(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, activate
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)

        def dependency_fails(point):
            if point == "after_tool_before_acknowledgment":
                activate("payment-service", "payment-unavailable")

        async with persistence.saver() as saver:
            report = await DurableExecution(
                durable_engine, persistence, saver, mcp, dependency_fails
            ).drive(run_id)
        assert report["status"] == "failed"
        assert report["verification"]["recovery_requires_new_approval"] is True
        assert counts(durable_engine)["effects"] == 1
        with Session(durable_engine) as session:
            assert session.scalar(
                select(Fault).where(Fault.service_name == "payment-service", Fault.active.is_(True))
            )

        class RecoveryFixture(FixtureDecisionModel):
            """Test-only dependency rule; no LLM inference."""

            async def generate(self, stage, context, schema):
                reply = await super().generate(stage, context, schema)
                observations = {o["tool_name"]: o for o in context["observations"]}
                names = ["get_service_metrics", "search_service_logs", "get_dependency_status"]
                refs = [observations[n]["id"] for n in names if n in observations]
                if stage == "evidence_assessment" and len(context["observations"]) == 5:
                    dependencies = observations["get_dependency_status"]["data"]["dependencies"]
                    assert (
                        next(d for d in dependencies if d["service_name"] == "payment-service")[
                            "metric"
                        ]["error_rate"]
                        >= 0.2
                    )
                    reply.value.hypotheses[0].description = "Payment dependency is failing."
                    reply.value.hypotheses[0].supporting_evidence = refs
                    reply.value.hypotheses[0].contradicting_evidence = []
                    reply.value.hypotheses[1].description = "Checkout workers remain saturated."
                    reply.value.hypotheses[1].supporting_evidence = []
                    reply.value.hypotheses[1].contradicting_evidence = [refs[0]]
                    reply.value.decision, reply.value.confidence = "propose", 0.8
                elif stage == "root_cause_proposal":
                    reply.value.service_name = ServiceName.PAYMENT
                    reply.value.explanation = (
                        "Payment requests fail and checkout propagates errors."
                    )
                elif stage == "remediation_planning":
                    reply.value.action = "reset_simulated_dependency"
                    reply.value.service_name = ServiceName.PAYMENT
                    reply.value.rationale = (
                        "Propose restoring the failed simulated payment dependency."
                    )
                return ModelReply(schema.model_validate(reply.value.model_dump()))

        async with connect(durable_stack[0], READER_TOKEN) as reader:
            recovery = await Investigation(
                RecoveryFixture(),
                reader,
                RunRequest(incident_id=investigation.incident_id, service_name="checkout-service"),
            ).run()
        assert recovery.run_status == "completed", recovery.errors
        recovery_id, next_approval = await start_run(
            durable_engine, persistence, mcp, recovery, recovery_of=run_id
        )
        assert next_approval != approval_id
        with pytest.raises(GatewayError):
            async with persistence.saver() as saver:
                await DurableExecution(durable_engine, persistence, saver, mcp).drive(recovery_id)
        assert counts(durable_engine)["effects"] == 1
        approve(durable_engine, durable_stack[1], next_approval, monkeypatch)
        async with persistence.saver() as saver:
            recovered = await DurableExecution(durable_engine, persistence, saver, mcp).drive(
                recovery_id
            )
        assert recovered["status"] == "verified"
        assert counts(durable_engine)["effects"] == counts(durable_engine)["verifications"] == 2
        Path("artifacts/stage4-separate-recovery-example.json").write_text(
            json.dumps(
                {
                    "synthetic_operator_test": True,
                    "failed_run": report,
                    "separately_approved_recovery": recovered,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def test_operator_authentication_has_no_model_or_noninteractive_bypass(monkeypatch):
    with pytest.raises(ExecutionError, match="AUTHENTICATION"):
        authenticate_operator(REGISTRY, "approved-by-the-model" + "x" * 40)
    with pytest.raises(ExecutionError, match="INTERACTIVE"):
        decide_interactively(None, None, REGISTRY, str(uuid4()), "approve")
    monkeypatch.setattr(getpass, "getuser", lambda: "different-os-account")
    with pytest.raises(ExecutionError, match="AUTHENTICATION"):
        authenticate_operator(REGISTRY, HUMAN_TOKEN)


@pytest.mark.anyio
async def test_raw_resume_value_cannot_create_human_approval(
    durable_engine, persistence, durable_stack, prepared
):
    from langgraph.types import Command

    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, _ = await start_run(durable_engine, persistence, mcp, investigation)
        async with persistence.saver() as saver, persistence.run_lock(run_id) as connection:
            execution = DurableExecution(durable_engine, persistence, saver, mcp)
            token = execution.lock_connection.set(connection)
            try:
                with pytest.raises(GatewayError):
                    await execution.graph.ainvoke(
                        Command(resume={"approved": True, "approver": "claimed-human"}),
                        {"configurable": {"thread_id": run_id}},
                        durability="sync",
                    )
            finally:
                execution.lock_connection.reset(token)
        assert counts(durable_engine)["effects"] == counts(durable_engine)["grants"] == 0


@pytest.mark.anyio
async def test_resource_changes_while_human_reviews_are_rejected(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, client, auth
):
    investigation, fault = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
    request = Repository(durable_engine).request(run_id)
    with monkeypatch.context() as patch:
        patch.setattr(sys.stdin, "isatty", lambda: True)
        patch.setattr(sys.stdout, "isatty", lambda: True)
        patch.setattr(getpass, "getpass", lambda _: HUMAN_TOKEN)

        def review(_):
            response = client.post(f"/api/v1/faults/{fault['id']}/deactivate", headers=auth)
            assert response.status_code == 200
            return f"APPROVE {request.fingerprint}"

        patch.setattr("builtins.input", review)
        with pytest.raises((ExecutionError, GatewayError)):
            decide_interactively(durable_engine, durable_stack[1], REGISTRY, approval_id, "approve")
    assert counts(durable_engine)["grants"] == counts(durable_engine)["effects"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "point", ["before_approval_restart", "after_approval", "after_tool_before_acknowledgment"]
)
async def test_hard_process_crash_and_new_process_recovery(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, tmp_path, point
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
        run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
    if point != "before_approval_restart":
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
    with durable_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPSPILOT_", "POSTGRES_", "LANGSMITH_", "LANGCHAIN_"))
    }
    output = tmp_path / "recovered-run.json"
    environment.update(
        {
            "OPSPILOT_CRASH_TEST_DATABASE_URL": durable_engine.url.render_as_string(
                hide_password=False
            ),
            "OPSPILOT_CRASH_TEST_SCHEMA": schema,
            "OPSPILOT_CRASH_TEST_RUN_ID": run_id,
            "OPSPILOT_CRASH_TEST_POINT": point,
            "OPSPILOT_CRASH_TEST_MCP_URL": durable_stack[0],
            "OPSPILOT_CRASH_TEST_TOKEN": EXECUTOR_TOKEN,
            "OPSPILOT_CRASH_TEST_OUTPUT": str(output),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        }
    )
    command = [sys.executable, str(Path(__file__).with_name("durable_crash_worker.py"))]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=90)
    assert first.returncode == 91, first.stderr[-2500:]
    assert counts(durable_engine)["effects"] == int(point == "after_tool_before_acknowledgment")
    if point == "before_approval_restart":
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
    environment["OPSPILOT_CRASH_TEST_POINT"] = "none"
    recovered = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=90)
    assert recovered.returncode == 0, recovered.stderr[-2500:]
    assert json.loads(output.read_text())["status"] == "verified"
    assert counts(durable_engine)["effects"] == counts(durable_engine)["verifications"] == 1


@pytest.mark.anyio
async def test_uncertain_timeout_reconciles_before_redelivery(
    durable_engine, persistence, durable_stack, prepared, monkeypatch
):
    investigation, _ = prepared
    async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as actual:
        run_id, approval_id = await start_run(durable_engine, persistence, actual, investigation)
        approve(durable_engine, durable_stack[1], approval_id, monkeypatch)

        class LoseAcknowledgment:
            offline = False
            action_calls = 0

            async def call(self, name, arguments):
                if self.offline:
                    raise TimeoutError
                value = await actual.call(name, arguments)
                if name == "restart_simulated_worker":
                    self.action_calls += 1
                    self.offline = True
                    raise TimeoutError
                return value

        lost = LoseAcknowledgment()
        async with persistence.saver() as saver:
            report = await DurableExecution(durable_engine, persistence, saver, lost).drive(run_id)
        assert report["status"] == "awaiting_reconciliation"
        assert lost.action_calls == counts(durable_engine)["effects"] == 1
        async with persistence.saver() as saver:
            final = await DurableExecution(durable_engine, persistence, saver, actual).drive(run_id)
        assert final["status"] == "verified"
        assert counts(durable_engine)["effects"] == 1
        with Session(durable_engine) as session:
            attempt = session.scalar(select(DurableAttempt).where(DurableAttempt.kind == "action"))
            assert attempt.outcome == "reconciled"


@pytest.mark.anyio
async def test_approval_and_audit_bindings_are_immutable_in_postgres(
    durable_engine, durable_stack, prepared
):
    from sqlalchemy.exc import DBAPIError

    investigation, _ = prepared
    repo = Repository(durable_engine)
    approval_id = repo.submit(investigation)
    with (
        pytest.raises(DBAPIError, match="immutable approval binding"),
        durable_engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE remediation_approvals SET fingerprint=:fp WHERE id=:id"),
            {"fp": "0" * 64, "id": approval_id},
        )
    with pytest.raises(DBAPIError, match="append only audit"), durable_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM durable_audit_events WHERE run_id=:id"),
            {"id": str(investigation.run_id)},
        )


@pytest.mark.anyio
async def test_restricted_worker_and_operator_can_run_without_service_write_access(
    durable_engine, persistence, durable_stack, prepared, monkeypatch
):
    from sqlalchemy import create_engine, event
    from sqlalchemy.exc import DBAPIError

    investigation, _ = prepared
    with durable_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    suffix = uuid4().hex[:20]
    worker_role, human_role = "opspilot_wr_" + suffix, "opspilot_hr_" + suffix
    roles = [worker_role, human_role]
    engines = []
    try:
        with durable_engine.begin() as connection:
            for role in roles:
                connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEROLE'))
                connection.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
                connection.execute(
                    text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
                )
                connection.execute(
                    text(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA "{schema}" TO "{role}"')
                )
            connection.execute(
                text(
                    f'GRANT INSERT ON "{schema}".durable_runs, '
                    f'"{schema}".durable_attempts, "{schema}".durable_audit_events '
                    f'TO "{worker_role}"'
                )
            )
            connection.execute(
                text(
                    f"GRANT INSERT (id,run_id,incident_id,tool,arguments,service_name,"
                    f"risk,evidence,preconditions,verification_plan,expires_at,"
                    f"fingerprint,created_at) "
                    f'ON "{schema}".remediation_approvals TO "{worker_role}"'
                )
            )
            connection.execute(
                text(
                    f"GRANT UPDATE (status,action_result,verification,updated_at) "
                    f'ON "{schema}".durable_runs TO "{worker_role}"'
                )
            )
            connection.execute(
                text(
                    f"GRANT UPDATE (outcome,finished_at) "
                    f'ON "{schema}".durable_attempts TO "{worker_role}"'
                )
            )
            connection.execute(
                text(
                    f'GRANT INSERT ON "{schema}".action_approvals, '
                    f'"{schema}".durable_audit_events TO "{human_role}"'
                )
            )
            connection.execute(
                text(
                    f"GRANT UPDATE (state,approved_by,approved_at,revoked_by,revoked_at) "
                    f'ON "{schema}".remediation_approvals TO "{human_role}"'
                )
            )

        def role_engine(role):
            engine = create_engine(
                durable_engine.url,
                hide_parameters=True,
                connect_args={"options": f"-csearch_path={schema}"},
            )

            @event.listens_for(engine, "connect")
            def assume_role(connection, record):
                with connection.cursor() as cursor:
                    cursor.execute(f'SET ROLE "{role}"')
                connection.commit()

            engines.append(engine)
            return engine

        worker, human = role_engine(worker_role), role_engine(human_role)
        async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
            run_id, approval_id = await start_run(worker, persistence, mcp, investigation)
            with (
                pytest.raises(DBAPIError, match="permission denied"),
                worker.begin() as connection,
            ):
                connection.execute(text("UPDATE remediation_approvals SET state='approved'"))
            approve(human, durable_stack[1], approval_id, monkeypatch)
            async with persistence.saver() as saver:
                report = await DurableExecution(worker, persistence, saver, mcp).drive(run_id)
            assert report["status"] == "verified"
            assert counts(durable_engine)["effects"] == 1
            for engine in [worker, human]:
                with engine.connect() as connection:
                    assert (
                        connection.scalar(
                            text("SELECT has_table_privilege(current_user,'services','UPDATE')")
                        )
                        is False
                    )
                    assert (
                        connection.scalar(
                            text("SELECT has_table_privilege(current_user,'faults','UPDATE')")
                        )
                        is False
                    )
    finally:
        for engine in engines:
            engine.dispose()
        # Only these two freshly generated NOLOGIN test roles are removed.
        with durable_engine.begin() as connection:
            for role in roles:
                connection.execute(text(f'DROP OWNED BY "{role}"'))
                connection.execute(text(f'DROP ROLE "{role}"'))
