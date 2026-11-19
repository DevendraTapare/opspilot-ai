"""Mock-provider contracts and fixture reasoning, never live-model verification."""

import asyncio
import copy
import json
import time

import httpx2
import pytest
from jsonschema import Draft202012Validator
from test_agent import FixtureMCP, run

from opspilot.agent import schemas
from opspilot.agent.diagnostics import ModelDiagnostic
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.provider_policy import (
    GroqCapacity,
    quota_scope,
    reset_seconds,
    strict_objects,
    validate_groq_request,
)
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure, strict_schema
from opspilot.agent.workflow import Investigation
from scripts.compare_groq_models import BASE, MODELS, StrictDiagnosis


def complete():
    captured = []
    fixture = FixtureDecisionModel()

    async def respond(req):
        body = json.loads(req.content)
        captured.append(body)
        validate_groq_request(body)
        payload = json.loads(body["messages"][-1]["content"])
        name = body.get("response_format", {}).get("json_schema", {}).get("name", "DiagnosticStep")
        reply = await fixture.generate(
            payload["stage"], payload["untrusted_investigation_context"], getattr(schemas, name)
        )
        if "tools" in body:
            message = {
                "tool_calls": [
                    {
                        "id": f"call_e_{len(captured)}",
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
            200,
            json={
                "choices": [{"finish_reason": reason, "message": message}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    model = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(respond),
    )
    result = run(model, FixtureMCP())
    assert result.run_status == "completed", result.errors
    return result, captured


def test_investigation_and_structured_phase_have_distinct_protocols_with_same_evidence():
    state, captured = complete()
    paired, assessed = False, False
    for body in captured:
        assert body["stream"] is False and body["include_reasoning"] is False
        assert "reasoning_format" not in body and body["max_tokens"] == 1600
        payload = json.loads(body["messages"][-1]["content"])
        context = payload["untrusted_investigation_context"]
        assert "tool_history" not in context
        if "tools" in body:
            assert body["parallel_tool_calls"] is False and "response_format" not in body
            paired |= any(m["role"] == "tool" for m in body["messages"])
        else:
            assert [m["role"] for m in body["messages"]] == ["system", "user"]
            assert not any(k in body for k in ("tools", "tool_choice", "parallel_tool_calls"))
            if payload["stage"] == "evidence_assessment":
                assessed = True
                for o in context["observations"]:
                    assert o == next(
                        v.model_dump(mode="json") for v in state.observations if v.id == o["id"]
                    )
    assert paired and assessed
    assert state.proposed_remediation.human_approval_required
    assert not state.recommendation.automatic_action_executed


def test_phase_b_still_rejects_substituted_tool_result_before_network():
    state, _ = complete()
    context = Investigation(None, None, state.request)._context(state)
    context["tool_history"][1]["request_id"] = "substituted"
    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(lambda _: pytest.fail("Network")),
    )
    with pytest.raises(ModelFailure) as error:
        asyncio.run(subject.generate("evidence_assessment", context, schemas.Assessment))
    assert error.value.diagnostic["category"] == "tool_result_binding"


@pytest.mark.parametrize(
    "schema",
    [
        schemas.Triage,
        schemas.Assessment,
        schemas.RootCause,
        schemas.Remediation,
        schemas.Recommendation,
        StrictDiagnosis,
    ],
)
def test_strict_schema_objects_and_definitions_remain_closed_and_satisfiable(schema):
    value = strict_schema(schema)
    strict_objects(value)
    Draft202012Validator.check_schema(value)
    if schema is StrictDiagnosis:
        state, _ = complete()
        packet = StrictDiagnosis(assessment=state.assessment, recommendation=state.recommendation)
        Draft202012Validator(value).validate(packet.model_dump(mode="json"))
        assert (
            value["$defs"]["Remediation"]["properties"]["human_approval_required"]["const"] is True
        )


@pytest.mark.parametrize("mutation", ["tools", "stream", "role", "fields", "open", "ref"])
def test_preflight_rejects_incompatible_requests(mutation):
    _, bodies = complete()
    body = copy.deepcopy(next(b for b in bodies if "response_format" in b))
    if mutation == "tools":
        body["tools"] = [{"type": "function"}]
    elif mutation == "stream":
        body["stream"] = True
    elif mutation == "role":
        body["messages"].insert(1, {"role": "tool", "content": "untrusted"})
    else:
        value = body["response_format"]["json_schema"]["schema"]
        if mutation == "fields":
            value["required"] = []
        elif mutation == "open":
            value["additionalProperties"] = True
        else:
            value["$ref"] = "https://invalid.example/private-schema"
    with pytest.raises(ValueError):
        validate_groq_request(body)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("52.342s", 52.342),
        ("1m2.5s", 62.5),
        ("24h", 86400),
        ("0s", 0),
        ("invalid private text", None),
        ("nan", None),
        ("100h", None),
        ("-1s", None),
        ("", None),
    ],
)
def test_provider_reset_duration_is_bounded(value, expected):
    assert reset_seconds(value) == expected


def test_token_reset_is_honored_even_when_some_tokens_remain():
    capacity = GroqCapacity()
    capacity.observe(
        {"x-ratelimit-reset-tokens": "52.342s", "x-ratelimit-remaining-tokens": "1021"},
        400,
        now=100,
    )
    assert capacity.delay(now=112) == pytest.approx(41.342)
    assert capacity.delay(now=154) == 0


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (429, {}, "MODEL_RATE_LIMITED"),
        (403, {}, "MODEL_ACCESS_DENIED"),
        (200, {"x-ratelimit-remaining-requests": "0"}, "MODEL_DAILY_LIMIT"),
    ],
)
def test_quota_and_access_failures_stop_subsequent_calls(status, headers, code):
    subject = HTTPDecisionModel(
        "groq", MODELS[1], BASE, "synthetic-key", request_interval_seconds=0
    )
    subject.capacity.observe(headers, status)
    with pytest.raises(ModelFailure, match=code):
        asyncio.run(subject.wait_for_capacity())


@pytest.mark.parametrize(
    "unit,label",
    [
        ("RPM", "requests_per_minute"),
        ("RPD", "requests_per_day"),
        ("TPM", "tokens_per_minute"),
        ("TPD", "tokens_per_day"),
    ],
)
def test_provider_limit_units_are_classified_without_saving_private_messages(unit, label):
    value = {"error": {"type": "tokens", "message": "private prefix (" + unit + ") private suffix"}}
    diagnostic = ModelDiagnostic()
    diagnostic.metadata(value, 429, {"x-ratelimit-remaining-requests": "996"})
    assert diagnostic.quota_scope == label
    assert diagnostic.quota_remaining_requests_per_day == 996
    assert "private" not in json.dumps(diagnostic.finish())


def test_unknown_quota_scope_does_not_invent_rpm_or_daily_limits():
    assert quota_scope({"error": {"type": "tokens"}}, 429) == "tokens_unspecified"
    assert quota_scope({}, 429) == "unclassified"
    assert quota_scope({}, 403) == "access_denied"


def test_header_wait_counts_toward_total_workflow_budget_without_network():
    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(lambda _: pytest.fail("Network")),
    )
    subject.capacity.not_before = time.monotonic() + 5
    result = run(subject, FixtureMCP(), max_seconds=0.5, call_timeout_seconds=0.1)
    assert result.run_status == "budget_exhausted" and result.usage.model_calls == 0
    assert result.proposed_remediation is None


def test_adapter_observes_token_reset_on_failed_schema_response_without_retry():
    calls = []

    def respond(req):
        calls.append(req)
        return httpx2.Response(
            400,
            json={"error": {"code": "json_validate_failed"}},
            headers={"x-ratelimit-reset-tokens": "52.342s"},
        )

    model = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(respond),
    )
    with pytest.raises(ModelFailure, match="MODEL_HTTP_ERROR"):
        asyncio.run(model.generate("triage", {}, schemas.Triage))
    assert len(calls) == 1 and model.capacity.delay() > 50


def test_live_plan_command_is_offline_and_bounded(monkeypatch, capsys):
    import scripts.verify_stage9e as subject

    monkeypatch.setattr("sys.argv", ["stage9e"])
    monkeypatch.setattr(subject, "load_key", lambda: pytest.fail("Credential read"))
    monkeypatch.setattr(subject, "execute", lambda *_: pytest.fail("Live execution"))
    assert subject.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["attempts"] == 1 and plan["maximum_provider_requests"] == 14
    assert plan["maximum_total_output_tokens"] == 14 * 1600
    assert plan["worst_case_list_price_estimate_usd"] < plan["maximum_reserved_usd"]


def test_live_wrapper_waits_for_budget_and_token_capacity_before_generation():
    from scripts.verify_stage9e import RecordedModel

    order = []

    class Budget:
        async def wait(self):
            order.append("budget")

    class Adapter:
        async def wait_for_capacity(self):
            order.append("capacity")

    subject = object.__new__(RecordedModel)
    subject.budget, subject.adapter = Budget(), Adapter()
    asyncio.run(subject.wait_for_capacity())
    assert order == ["budget", "capacity"]


def test_live_ledger_records_stream_and_protocol_flags_without_prompts(tmp_path):
    from pydantic import SecretStr

    from scripts.verify_stage9e import ExperimentBudget

    _, bodies = complete()
    budget = ExperimentBudget(tmp_path, SecretStr("synthetic-key"))
    body = next(b for b in bodies if "response_format" in b)
    row = budget.reserve(body, "fixture:assessment")
    assert row["stream"] is False and row["contains_tool_protocol"] is False
    assert "messages" not in row and "Authorization" not in json.dumps(row)


@pytest.mark.parametrize("finish", ["tool_calls", "stop"])
def test_structured_phase_cannot_accept_an_unrequested_tool_response(finish):
    response = {
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "content": schemas.Triage(
                        summary="Fixture", alternatives=["a", "b"]
                    ).model_dump_json(),
                    "tool_calls": [
                        {"id": "unexpected", "function": {"name": "restart_simulated_worker"}}
                    ],
                },
            }
        ]
    }
    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=response)),
    )
    with pytest.raises(ModelFailure):
        asyncio.run(subject.generate("triage", {}, schemas.Triage))
