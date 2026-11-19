"""Response/lifecycle regressions using mocked models, never genuine LLM claims."""

import asyncio
import json

import httpx2
import pytest
from test_agent import FixtureMCP, request, run

from opspilot.agent.conversation import tool_messages
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import DiagnosticStep, InvestigationState, ModelToolCall, Triage


def complete_http_investigation():
    captured = []
    fixture = FixtureDecisionModel()

    async def respond(http_request):
        body = json.loads(http_request.content)
        captured.append(body)
        payload = json.loads(body["messages"][-1]["content"])
        stage, context = payload["stage"], payload["untrusted_investigation_context"]
        from opspilot.agent import schemas

        schema = getattr(
            schemas,
            body.get("response_format", {}).get("json_schema", {}).get("name", "DiagnosticStep"),
        )
        reply = await fixture.generate(stage, context, schema)
        if "tools" in body:
            assert "response_format" not in body
            message = {
                "tool_calls": [
                    {
                        "id": f"call_{len(captured)}",
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
            assert body["response_format"]["json_schema"]["strict"] is True
            message = {"content": reply.value.model_dump_json()}
            reason = "stop"
        return httpx2.Response(
            200,
            json={
                "choices": [{"finish_reason": reason, "message": message}],
                "usage": {"prompt_tokens": 99, "completion_tokens": 22},
            },
        )

    model = HTTPDecisionModel(
        "groq",
        "qwen/qwen3.8-27b",
        "https://api.groq.com/openai/v1",
        "synthetic-test-key",
        transport=httpx2.MockTransport(respond),
        request_interval_seconds=0,
    )
    result = run(model, FixtureMCP())
    assert result.run_status == "completed", result.errors
    return result, captured


def test_full_tool_lifecycle_and_evidence_survive_state_serialization():
    result, captured = complete_http_investigation()
    restored = InvestigationState.model_validate_json(result.model_dump_json())
    assert restored.evidence_references == ["e001", "e002", "e003", "e004", "e005"]
    calls = restored.tool_call_history[1:]
    assert len({c.model_call.id for c in calls}) == 4
    for call in calls:
        observation = next(o for o in restored.observations if o.id == call.evidence_ref)
        assert call.request_id == observation.request_id
        assert call.model_call.arguments.tool_name == call.tool_name
    paired = 0
    for body in captured:
        assert body["reasoning_effort"] == "none" and body["reasoning_format"] == "hidden"
        messages = body["messages"]
        for index, message in enumerate(messages):
            if message["role"] != "tool":
                continue
            previous = messages[index - 1]["tool_calls"][0]
            assert previous["id"] == message["tool_call_id"]
            response = json.loads(message["content"])
            observation = next(o for o in restored.observations if o.id == response["evidence_ref"])
            assert response["request_id"] == observation.request_id
            assert "observation" not in response  # Full data occurs once in validated context.
            paired += 1
        stage = json.loads(messages[-1]["content"])["stage"]
        if stage in {"root_cause_proposal", "remediation_planning"}:
            assert "tools" not in body and all(m["role"] != "tool" for m in messages)
    assert paired > 0
    assert restored.proposed_remediation.human_approval_required
    assert not restored.recommendation.automatic_action_executed


@pytest.mark.parametrize("mutation", ["reference", "request_id", "duplicate_call_id", "arguments"])
def test_transcript_rejects_substituted_results_or_tool_ids(mutation):
    result, _ = complete_http_investigation()
    context = {
        "incident_id": str(result.incident_id),
        "allowed_services": ["checkout-service"],
        "observations": [o.model_dump(mode="json") for o in result.observations],
        "tool_history": [t.model_dump(mode="json") for t in result.tool_call_history],
    }
    if mutation == "reference":
        context["tool_history"][1]["evidence_ref"] = "e003"
    elif mutation == "request_id":
        context["tool_history"][1]["request_id"] = "different-request"
    elif mutation == "duplicate_call_id":
        context["tool_history"][2]["model_call"]["id"] = context["tool_history"][1]["model_call"][
            "id"
        ]
    else:
        context["tool_history"][1]["model_call"]["arguments"]["service_name"] = "payment-service"
    with pytest.raises(ValueError):
        tool_messages(context)


def test_citation_wire_enum_contains_only_observed_ids():
    result, captured = complete_http_investigation()
    for body in captured:
        if "response_format" not in body:
            continue
        payload = json.loads(body["messages"][-1]["content"])
        expected = [o["id"] for o in payload["untrusted_investigation_context"]["observations"]]

        def inspect(node, expected=expected):
            if isinstance(node, dict):
                if node.get("pattern") == r"^e[0-9]{3}$":
                    assert node["enum"] == expected
                    assert "e999" not in node["enum"]
                for child in node.values():
                    inspect(child)
            elif isinstance(node, list):
                for child in node:
                    inspect(child)

        inspect(body["response_format"])
    assert result.evidence_references


@pytest.mark.parametrize(
    "message,reason,code",
    [
        ({"content": "{broken"}, "stop", "MODEL_OUTPUT_INVALID"),
        ({"content": ""}, "stop", "MODEL_EMPTY_RESPONSE"),
        ({"content": None, "refusal": "Untrusted refusal text"}, "stop", "MODEL_REFUSED"),
        ({"content": "{}"}, "length", "MODEL_OUTPUT_INCOMPLETE"),
    ],
)
def test_malformed_empty_refusal_and_truncation_are_explicit(message, reason, code):
    model = HTTPDecisionModel(
        "groq",
        "qwen/qwen3.8-27b",
        "https://api.groq.com/openai/v1",
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "choices": [{"finish_reason": reason, "message": message}],
                },
            )
        ),
    )
    with pytest.raises(ModelFailure, match=code):
        asyncio.run(model.generate("triage", {}, Triage))


def test_rate_limit_is_not_retried_or_substituted():
    requests = []

    def respond(http_request):
        requests.append(http_request)
        return httpx2.Response(429, json={"error": "sensitive error details"})

    model = HTTPDecisionModel(
        "groq",
        "qwen/qwen3.8-27b",
        "https://api.groq.com/openai/v1",
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(respond),
    )
    with pytest.raises(ModelFailure, match="MODEL_RATE_LIMITED") as failure:
        asyncio.run(model.generate("triage", {}, Triage))
    assert len(requests) == 1 and "sensitive" not in str(failure.value)


def test_function_call_without_provider_id_is_rejected():
    step = DiagnosticStep(
        tool_name="get_service_metrics", service_name="checkout-service", rationale="Check metrics"
    )
    model = HTTPDecisionModel(
        "openai-compatible",
        "mock",
        "http://localhost:1234/v1",
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "select_diagnostic_tool",
                                            "arguments": step.model_dump_json(),
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                },
            )
        ),
    )
    with pytest.raises(ModelFailure, match="MODEL_OUTPUT_INVALID"):
        asyncio.run(model.generate("investigation_planning", {}, DiagnosticStep))


def test_pacing_is_charged_to_total_budget_before_another_request():
    class SlowCapacity(FixtureDecisionModel):
        async def wait_for_capacity(self):
            await asyncio.sleep(1)

    from opspilot.agent.workflow import Investigation

    result = asyncio.run(
        Investigation(
            SlowCapacity(),
            FixtureMCP(),
            request(max_seconds=0.1, call_timeout_seconds=0.05),
        ).run()
    )
    assert result.run_status == "budget_exhausted" and result.usage.model_calls == 0
    assert result.proposed_remediation is None


def test_invented_well_formed_citation_is_not_rebound_to_real_evidence():
    class InventedCitation(FixtureDecisionModel):
        async def generate(self, stage, context, schema):
            reply = await super().generate(stage, context, schema)
            if stage == "root_cause_proposal":
                reply.value = reply.value.model_copy(update={"evidence_refs": ["e002", "e999"]})
            return reply

    result = run(InventedCitation())
    assert result.run_status == "abstained"
    assert "e999" not in result.evidence_references
    assert result.candidate_root_cause is None and result.proposed_remediation is None


def test_model_function_argument_mismatch_is_rejected_before_mcp():
    class MismatchedFunction(FixtureDecisionModel):
        async def generate(self, stage, context, schema):
            reply = await super().generate(stage, context, schema)
            if stage == "investigation_planning":
                reply.tool_call = ModelToolCall(
                    id="call_substituted",
                    arguments=reply.value.model_copy(update={"service_name": "payment-service"}),
                )
            return reply

    mcp = FixtureMCP()
    result = run(MismatchedFunction(), mcp)
    assert result.run_status == "abstained" and len(mcp.calls) == 1
    assert mcp.calls[0][0] == "get_incident"


def test_duplicate_registry_ids_cannot_survive_into_model_context():
    from opspilot.agent.workflow import Investigation

    result, _ = complete_http_investigation()
    result.observations[1].id = result.observations[0].id
    with pytest.raises(ValueError, match="registry integrity"):
        Investigation(FixtureDecisionModel(), FixtureMCP(), result.request)._context(result)
