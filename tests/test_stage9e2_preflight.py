"""Cost admission/runner preflight with mocked HTTP only; no paid requests."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx2
import pytest
from test_agent import FixtureMCP, run

from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import Triage
from scripts.stage9e2_budget import BASE, MODEL, GuardedTransport, ReservationGuard
from scripts.verify_stage9e2 import LIMITS, PLAN, review_candidate


def body():
    model = HTTPDecisionModel("groq", MODEL, BASE, "synthetic-test", request_interval_seconds=0)
    return model.prepare_request("triage", {}, Triage)[0]


def test_plan_mode_loads_no_credentials_and_calls_no_network(monkeypatch, capsys):
    from scripts import verify_stage9e2

    monkeypatch.setattr("sys.argv", ["verify_stage9e2"])
    monkeypatch.setattr(verify_stage9e2, "execute", lambda _: pytest.fail("Live path forbidden"))
    assert verify_stage9e2.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["approval"] == "Required; not approved"
    assert plan["model"] == MODEL and plan["investigations"] == 1
    assert LIMITS["max_model_calls"] == 11 and LIMITS["max_tool_calls"] == 5
    assert plan["maximum_cumulative_output_tokens"] == 17600
    assert not plan["remediation_execution"] and not plan["default_model_change"]
    assert plan["local_reservation_ceiling_usd"] == 0.02
    assert not plan["invoice_guarantee"]
    assert (
        PLAN["maximum_estimated_list_price_usd"]
        == ((160000 - 17600) * 0.075 + 17600 * 0.30) / 1_000_000
    )


def test_cost_block_is_before_dispatch_with_unknown_usage(tmp_path):
    probe = ReservationGuard(tmp_path)
    r = probe.reserve(body(), "triage")
    amount = r["reserved_nanodollars"]
    probe.finish(r, status=200, value={})
    assert probe.charged == amount and not probe.rows[0]["cost_complete"]
    probe.ceiling = amount * 2 - 1  # Simulate a nearly exhausted fixed ceiling.
    sent = []

    async def downstream(request):
        sent.append(request)
        pytest.fail("Over-budget request reached downstream")

    async def attempt():
        async with httpx2.AsyncClient(
            transport=GuardedTransport(probe, "triage", httpx2.MockTransport(downstream))
        ) as client:
            await client.post(BASE + "/chat/completions", json=body())

    with pytest.raises(ModelFailure, match="COST_BUDGET_EXHAUSTED"):
        asyncio.run(attempt())
    assert not sent and len(probe.rows) == 1 and probe.charged == amount


def test_low_usage_never_refunds_reservations(tmp_path):
    guard = ReservationGuard(tmp_path)
    row = guard.reserve(body(), "triage")
    amount = guard.charged
    guard.finish(row, status=200, value={"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    assert guard.charged == amount
    assert row["cost_complete"] and row["reported_list_price_nanodollars"] == 375


@pytest.mark.parametrize("status", [400, 413, 429, 401, 403, 500])
def test_every_provider_error_stops_before_second_dispatch(tmp_path, status):
    guard, calls = ReservationGuard(tmp_path), []

    def actual(request):
        # Ledger already exists with reservation when transport receives request.
        disk = json.loads((tmp_path / "requests.json").read_text())
        assert disk["accounted_nanodollars"] > 0 and len(disk["requests"]) == 1
        calls.append(request)
        return httpx2.Response(
            status, json={"error": {"code": "rate_limit_exceeded", "type": "tokens"}}
        )

    async def twice():
        for _ in range(2):
            async with httpx2.AsyncClient(
                transport=GuardedTransport(guard, "triage", httpx2.MockTransport(actual))
            ) as client:
                await client.post(BASE + "/chat/completions", json=body())

    with pytest.raises(ModelFailure):
        asyncio.run(twice())
    assert len(calls) == 1 and guard.rows[0]["http_status"] == status
    assert not guard.rows[0]["cost_complete"]


@pytest.mark.parametrize(
    "field,value", [("model", "other"), ("n", 2), ("stream", True), ("max_tokens", 1600.0)]
)
def test_profile_cannot_increase_cost_or_change_model(tmp_path, field, value):
    guard = ReservationGuard(tmp_path)
    altered = body()
    altered[field] = value
    with pytest.raises((ValueError, ModelFailure)):
        guard.reserve(altered, "triage")
    assert guard.charged == 0 and not guard.rows


@pytest.mark.parametrize("limit", ["requests", "prompt", "tokens", "deadline"])
def test_all_other_limits_block_before_dispatch(tmp_path, limit):
    guard = ReservationGuard(tmp_path)
    altered = body()
    if limit == "requests":
        guard.rows = [{}] * 11
    elif limit == "prompt":
        altered["messages"][-1]["content"] += "x" * 20000
    elif limit == "tokens":
        guard.estimated_tokens = 159999
    else:
        guard.started = time.monotonic() - 601
    with pytest.raises(ModelFailure):
        guard.reserve(altered, "triage")
    assert guard.charged == 0


def test_existing_ledger_cannot_be_reinitialized(tmp_path):
    guard = ReservationGuard(tmp_path)
    guard.reserve(body(), "triage")
    with pytest.raises(FileExistsError):
        ReservationGuard(tmp_path)


def test_concurrent_calls_cannot_double_admit(tmp_path):
    guard = ReservationGuard(tmp_path)

    def reserve():
        try:
            return guard.reserve(body(), "triage")
        except ModelFailure:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve(), range(2)))
    assert sum(r is not None for r in results) == 1 and len(guard.rows) == 1


def test_reported_overage_stops_and_does_not_hide_invoice_limitation(tmp_path):
    guard = ReservationGuard(tmp_path)
    row = guard.reserve(body(), "triage")
    guard.finish(
        row, status=200, value={"usage": {"prompt_tokens": 999999, "completion_tokens": 1600}}
    )
    assert guard.stopped == "USAGE_EXCEEDED_RESERVATION"
    assert guard.charged > guard.ceiling  # Already-reported charge cannot be undone.
    with pytest.raises(ModelFailure):
        guard.reserve(body(), "triage")


def test_failed_persistence_prevents_dispatch(tmp_path, monkeypatch):
    guard = ReservationGuard(tmp_path)

    def fail():
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(guard, "persist", fail)
    with pytest.raises(ModelFailure, match="LEDGER_PERSISTENCE_FAILED"):
        guard.reserve(body(), "triage")


def test_timeout_retains_unknown_reservation_and_blocks_another_request(tmp_path):
    guard, calls = ReservationGuard(tmp_path), []

    def fail(request):
        calls.append(request)
        raise httpx2.ReadTimeout("Synthetic timeout")

    async def send():
        async with httpx2.AsyncClient(
            transport=GuardedTransport(guard, "triage", httpx2.MockTransport(fail))
        ) as client:
            await client.post(BASE + "/chat/completions", json=body())

    with pytest.raises(httpx2.ReadTimeout):
        asyncio.run(send())
    amount = guard.charged
    assert amount > 0 and not guard.rows[0]["cost_complete"]
    with pytest.raises(ModelFailure):
        asyncio.run(send())
    assert len(calls) == 1 and guard.charged == amount


def test_invalid_structured_output_latches_stop_without_retry(tmp_path, monkeypatch):
    from scripts import verify_stage9e2

    guard, calls = ReservationGuard(tmp_path), []

    def invalid(request):
        calls.append(request)
        return httpx2.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]}
        )

    monkeypatch.setattr(
        verify_stage9e2,
        "GuardedTransport",
        lambda g, s: GuardedTransport(g, s, httpx2.MockTransport(invalid)),
    )
    model = verify_stage9e2.RecordedModel(guard, "synthetic-test")
    model.adapter.request_interval_seconds = 0
    for _ in range(2):
        with pytest.raises(ModelFailure):
            asyncio.run(model.generate("triage", {"observations": []}, Triage))
    assert len(calls) == 1 and len(guard.rows) == 1


def test_local_ceiling_cannot_be_configured_back_to_old_005_limit(tmp_path):
    with pytest.raises(ValueError):
        ReservationGuard(tmp_path, ceiling=50_000_000)


def test_supported_diagnosis_and_explicit_abstention_still_need_review():
    completed = run()
    assert review_candidate(completed, True) == "DIAGNOSIS_REQUIRES_INDEPENDENT_REVIEW"
    abstained = run(mcp=FixtureMCP(degraded=False))
    assert review_candidate(abstained, True) == "ABSTENTION_REQUIRES_INDEPENDENT_REVIEW"
    for state in [run(max_model_calls=1), run(max_estimated_tokens=1)]:
        assert review_candidate(state, True) == "FAILURE_OR_INCOMPLETE"
    assert review_candidate(completed, False) == "FAILURE_OR_INCOMPLETE"


def test_entire_planned_workflow_fits_local_limits_with_mock_inference(tmp_path, monkeypatch):
    from test_agent import request

    from opspilot.agent import schemas
    from opspilot.agent.fixtures import FixtureDecisionModel
    from opspilot.agent.workflow import Investigation
    from scripts import verify_stage9e2

    fixture = FixtureDecisionModel()
    guard = ReservationGuard(tmp_path)

    async def respond(request):
        data = json.loads(request.content)
        payload = json.loads(data["messages"][-1]["content"])
        name = data.get("response_format", {}).get("json_schema", {}).get("name", "DiagnosticStep")
        reply = await fixture.generate(
            payload["stage"], payload["untrusted_investigation_context"], getattr(schemas, name)
        )
        if "tools" in data:
            message = {
                "tool_calls": [
                    {
                        "id": f"offline_{len(guard.rows)}",
                        "type": "function",
                        "function": {
                            "name": "select_diagnostic_tool",
                            "arguments": reply.value.model_dump_json(),
                        },
                    }
                ]
            }
            reason = "tool_calls"
        else:
            message, reason = {"content": reply.value.model_dump_json()}, "stop"
        return httpx2.Response(
            200, json={"choices": [{"finish_reason": reason, "message": message}]}
        )

    monkeypatch.setattr(
        verify_stage9e2,
        "GuardedTransport",
        lambda g, stage: GuardedTransport(g, stage, httpx2.MockTransport(respond)),
    )
    model = verify_stage9e2.RecordedModel(guard, "synthetic-test")
    model.mode = "fixture"
    model.adapter.request_interval_seconds = 0
    state = asyncio.run(Investigation(model, FixtureMCP(), request(**LIMITS)).run())
    assert state.run_status == "completed", state.errors
    assert len(guard.rows) == 11 and len(state.tool_call_history) == 5
    assert guard.charged <= 15_960_000 < guard.ceiling
    assert all(not row["cost_complete"] for row in guard.rows)
    assert len(model.decisions) == 11
    assert not state.recommendation.automatic_action_executed
