"""Budget/security contracts with mocks; no provider inference or account credential."""

import asyncio
import gzip
import json
import secrets

import httpx2
import pytest
from pydantic import SecretStr
from test_agent import run

from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from scripts.compare_groq_models import (
    BASE,
    MODELS,
    Budget,
    StrictDiagnosis,
    probe,
    settings,
    validate_diagnosis,
)


def body(model=MODELS[0]):
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Harmless test"}],
        **settings(model),
    }


def test_global_request_cap_includes_model_list_and_failed_attempts(tmp_path):
    budget = Budget(tmp_path, SecretStr("synthetic-key"), request_limit=2)
    budget.reserve(None, "availability")
    budget.reserve(body(), "probe:A")
    with pytest.raises(ModelFailure, match="REQUEST_BUDGET_EXHAUSTED"):
        budget.reserve(body(MODELS[1]), "probe:A")
    assert len(budget.requests) == 2


def test_cost_ceiling_is_reserved_before_sending_request(tmp_path):
    budget = Budget(tmp_path, SecretStr("synthetic-key"), cost_limit=0.00001)
    with pytest.raises(ModelFailure, match="COST_BUDGET_EXHAUSTED"):
        budget.reserve(body(), "probe:A")
    assert budget.requests == []


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("model", "MODEL_NOT_ALLOWLISTED"),
        ("parallel", "PARALLEL_TOOLS_REJECTED"),
        ("mixed", "TOOLS_AND_STRUCTURED_OUTPUT_REJECTED"),
    ],
)
def test_unsafe_request_shapes_rejected_before_accounting(tmp_path, mutation, code):
    budget = Budget(tmp_path, SecretStr("synthetic-key"))
    value = body()
    if mutation == "model":
        value["model"] = "unapproved/model"
    else:
        value["tools"] = [{"type": "function"}]
        if mutation == "mixed":
            value["parallel_tool_calls"] = False
            value["response_format"] = {"type": "json_schema"}
    with pytest.raises(ModelFailure, match=code):
        budget.reserve(value, "probe:B")
    assert budget.requests == []


def test_model_specific_settings_are_explicit_without_default_switch():
    qwen, gpt = (settings(m) for m in MODELS)
    assert qwen["reasoning_effort"] == gpt["reasoning_effort"] == "medium"
    assert qwen["reasoning_format"] == "hidden" and "include_reasoning" not in qwen
    assert gpt["include_reasoning"] is False and "reasoning_format" not in gpt
    assert HTTPDecisionModel("groq", MODELS[0], BASE, "synthetic-key").reasoning_effort == "none"
    with pytest.raises(ValueError):
        HTTPDecisionModel("groq", MODELS[1], BASE, "synthetic-key", reasoning_effort="none")


def test_private_provider_reasoning_and_credentials_are_not_recorded(tmp_path):
    secret = "test-marker-" + secrets.token_hex(16)
    budget = Budget(tmp_path, SecretStr(secret))
    value = body()
    request = httpx2.Request(
        "POST",
        BASE + "/chat/completions",
        json=value,
        headers={"Authorization": "Bearer " + secret},
    )
    actual = httpx2.MockTransport(
        lambda _: httpx2.Response(
            200,
            json={
                "model": MODELS[0],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "Final answer", "reasoning": secret},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )
    asyncio.run(budget.exchange(request, value, "probe:A", actual))
    assert secret not in (tmp_path / "requests.json").read_text()
    assert budget.requests[0]["input_tokens"] == 10
    assert budget.requests[0]["cost_complete"]


def test_compressed_provider_json_is_decoded_exactly_once(tmp_path):
    budget = Budget(tmp_path, SecretStr("synthetic-key"))
    payload = {"data": [{"id": MODELS[0], "active": True}]}
    actual = httpx2.MockTransport(
        lambda _: httpx2.Response(
            200,
            content=gzip.compress(json.dumps(payload).encode()),
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        )
    )
    result = asyncio.run(
        budget.exchange(httpx2.Request("GET", BASE + "/models"), None, "availability", actual)
    )
    assert result.json() == payload and "content-encoding" not in result.headers


def test_probe_cannot_dispatch_cross_service_tool_arguments(tmp_path):
    class ModelStub:
        async def call(self, *_):
            return {
                "tool_calls": [
                    {
                        "id": "call_fixture",
                        "type": "function",
                        "function": {
                            "name": "get_service_health",
                            "arguments": json.dumps({"service_name": "payment-service"}),
                        },
                    }
                ]
            }

    class NoMCP:
        async def call(self, *_):
            pytest.fail("Invalid target reached MCP")

    result = asyncio.run(probe(ModelStub(), MODELS[0], "B", NoMCP(), None))
    assert not result["passed"] and result["error_code"] == "MODEL_TOOL_SCOPE_INVALID"


def test_existing_diagnosis_guards_accept_bound_evidence_and_reject_fabrication():
    state = run()
    packet = StrictDiagnosis(assessment=state.assessment, recommendation=state.recommendation)
    assert validate_diagnosis(packet, state).recommendation.status == "completed"
    packet.recommendation.root_cause.evidence_refs = ["e002", "e999"]
    with pytest.raises(ValueError):
        validate_diagnosis(packet, state)
