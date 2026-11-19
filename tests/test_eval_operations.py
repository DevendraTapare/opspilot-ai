# ruff: noqa: F811
"""Measured operational probes. Test humans never authorize a runtime/main database."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_durable import (  # noqa: F401 -- pytest fixtures are intentionally reused
    EXECUTOR_TOKEN,
    REGISTRY,
    anyio_backend,
    approve,
    counts,
    durable_engine,
    durable_stack,
    persistence,
    prepared,
    start_run,
)
from test_durable import (
    test_action_success_but_verification_failure_requires_separate_recovery as failed_recovery,
)
from test_durable import (
    test_hard_process_crash_and_new_process_recovery as hard_recovery,
)
from test_durable import (
    test_raw_resume_value_cannot_create_human_approval as raw_bypass,
)

from evaluations.runners.operations import record
from opspilot.durable.client import connect_executor
from opspilot.durable.repository import Repository
from opspilot.durable.workflow import DurableExecution
from opspilot.models import RemediationVerification


def verification_judgments(engine, expected):
    with Session(engine) as session:
        actual = [
            v.result["outcome"]
            for v in session.scalars(
                select(RemediationVerification).order_by(RemediationVerification.created_at)
            )
        ]
    assert actual == expected
    return [{"actual": a, "expected": e} for a, e in zip(actual, expected, strict=True)]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["rejection", "unauthorized", "bypass", "duplicate", "stale"])
async def test_measured_security(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, kind, client, auth
):
    row = {
        "id": "security-" + kind,
        "kind": "security",
        "unauthorized_effects": 0,
        "bypass_attempts": int(kind == "bypass"),
        "unauthorized_attempts": int(kind in {"unauthorized", "bypass"}),
        "rejection_expected": kind != "duplicate",
        "correct_rejection": kind != "duplicate",
    }
    if kind == "bypass":
        await raw_bypass(durable_engine, persistence, durable_stack, prepared)
    else:
        investigation, fault = prepared
        async with connect_executor(durable_stack[0], EXECUTOR_TOKEN) as mcp:
            run_id, approval_id = await start_run(durable_engine, persistence, mcp, investigation)
            request = Repository(durable_engine).request(run_id)
            if kind in {"duplicate", "stale"}:
                approve(durable_engine, durable_stack[1], approval_id, monkeypatch)
            if kind == "rejection":
                import getpass
                import sys

                from test_durable import HUMAN_TOKEN

                from opspilot.durable.operator import decide_interactively

                monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
                monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
                monkeypatch.setattr(getpass, "getpass", lambda _: HUMAN_TOKEN)
                monkeypatch.setattr("builtins.input", lambda _: "REVOKE " + request.fingerprint)
                decide_interactively(
                    durable_engine, durable_stack[1], REGISTRY, approval_id, "revoke"
                )
            if kind == "stale":
                assert (
                    client.post(
                        f"/api/v1/faults/{fault['id']}/deactivate", headers=auth
                    ).status_code
                    == 200
                )
            if kind == "duplicate":
                async with persistence.saver() as saver:
                    result = await DurableExecution(durable_engine, persistence, saver, mcp).drive(
                        run_id
                    )
                assert result["status"] == "verified"
            before = counts(durable_engine)["effects"]
            result = await mcp.call(request.tool, request.arguments)
            after = counts(durable_engine)["effects"]
            assert not result["ok"]
            assert before == after == int(kind == "duplicate")
            row["actual_error_code"] = result["error"]["code"]
            row["unauthorized_effects"] = after - before
            row["duplicate_effects"] = max(0, after - 1) if kind == "duplicate" else 0
            row["replay_or_recovery"] = kind == "duplicate"
            if kind == "duplicate":
                row["verification_judgments"] = verification_judgments(durable_engine, ["verified"])
    row["effects_after"] = counts(durable_engine)["effects"]
    record(row)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "point", ["before_approval_restart", "after_approval", "after_tool_before_acknowledgment"]
)
async def test_measured_hard_recovery(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, tmp_path, point
):
    await hard_recovery(
        durable_engine, persistence, durable_stack, prepared, monkeypatch, tmp_path, point
    )
    effects = counts(durable_engine)["effects"]
    record(
        {
            "id": "recovery-" + point,
            "kind": "recovery",
            "recovered": effects == 1,
            "replay_or_recovery": True,
            "duplicate_effects": max(0, effects - 1),
            "effects_after": effects,
            "verification_judgments": verification_judgments(durable_engine, ["verified"]),
        }
    )


@pytest.mark.anyio
async def test_measured_failed_verification(
    durable_engine, persistence, durable_stack, prepared, monkeypatch, activate
):
    await failed_recovery(
        durable_engine, persistence, durable_stack, prepared, monkeypatch, activate
    )
    record(
        {
            "id": "verification-failure-and-independent-recovery",
            "kind": "verification",
            "effects_after": counts(durable_engine)["effects"],
            "verification_judgments": verification_judgments(
                durable_engine, ["failed", "verified"]
            ),
        }
    )
