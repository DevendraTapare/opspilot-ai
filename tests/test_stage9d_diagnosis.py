"""Offline contracts: mock HTTP/fixture evidence, never real-model reasoning."""

import asyncio
import json
import secrets

import httpx2
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_agent import NOW, metric, run

from opspilot.agent.conversation import bind_citation_schema
from opspilot.agent.diagnostics import ModelDiagnostic
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure, strict_schema
from scripts.compare_groq_models import BASE, MODELS, StrictDiagnosis, validate_diagnosis
from scripts.diagnose_stage9d import (
    PLAN,
    BasicJSON,
    DiagnosticBudget,
    MinimalDiagnosis,
    full_messages,
    isolated_probes,
    main,
    structured,
)


def packet():
    state = run()
    value = StrictDiagnosis(assessment=state.assessment, recommendation=state.recommendation)
    return state, value.model_dump(mode="json")


def wire(state):
    return bind_citation_schema(strict_schema(StrictDiagnosis), state.evidence_references)


def adapter(response):
    return HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(lambda _: response),
    )


def envelope(content, finish="stop"):
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-12345678",
            "choices": [{"finish_reason": finish, "message": {"content": content}}],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 32,
                "completion_tokens_details": {"reasoning_tokens": 10},
            },
        },
        headers={"x-request-id": "req_12345678"},
    )


def test_full_schema_is_satisfiable_and_preserves_required_and_citation_constraints():
    state, value = packet()
    schema = wire(state)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
    validate_diagnosis(value, state)

    def visit(node):
        if isinstance(node, dict):
            assert "default" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            if node.get("pattern") == r"^e[0-9]{3}$":
                assert node["enum"] == state.evidence_references
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)


@pytest.mark.parametrize(
    "mutation", ["required", "type", "extra", "citation", "approval", "action"]
)
def test_invalid_fixtures_fail_wire_schema(mutation):
    state, value = packet()
    if mutation == "required":
        del value["assessment"]["confidence"]
    elif mutation == "type":
        value["assessment"]["confidence"] = "high"
    elif mutation == "extra":
        value["assessment"]["unknown"] = "value"
    elif mutation == "citation":
        value["recommendation"]["root_cause"]["evidence_refs"][0] = "e999"
    elif mutation == "approval":
        value["recommendation"]["proposed_remediation"]["human_approval_required"] = False
    else:
        value["recommendation"]["automatic_action_executed"] = True
    assert list(Draft202012Validator(wire(state)).iter_errors(value))


@pytest.mark.parametrize(
    "content,category",
    [
        ("", "empty_response"),
        ("{", "response_parsing"),
        ('{"assessment":', "response_parsing"),
        ("no JSON", "response_parsing"),
        ("{}", "schema_validation"),
        ("[]", "schema_validation"),
    ],
)
def test_parser_and_schema_failures_are_distinct(content, category):
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(adapter(envelope(content)).generate("diagnosis", {}, StrictDiagnosis))
    assert caught.value.diagnostic["category"] == category
    assert caught.value.diagnostic["request_id"] == "req_12345678"
    assert caught.value.diagnostic["timings_ms"]["total"] >= 0


@pytest.mark.parametrize("content", [None, 1, [], {"unexpected": "value"}])
def test_non_text_content_is_rejected(content):
    with pytest.raises(ModelFailure):
        asyncio.run(adapter(envelope(content)).generate("diagnosis", {}, StrictDiagnosis))


def test_schema_valid_but_unsupported_diagnosis_is_not_grounded():
    state, value = packet()
    value["assessment"]["hypotheses"][0]["contradicting_evidence"] = ["e001"]
    Draft202012Validator(wire(state)).validate(value)
    with pytest.raises(ValueError):
        validate_diagnosis(value, state)


def test_fabricated_citation_is_evidence_failure_not_json_failure():
    state, value = packet()
    value["recommendation"]["root_cause"]["evidence_refs"][0] = "e999"
    StrictDiagnosis.model_validate(value)  # The ID has valid syntax but does not exist.
    with pytest.raises(ValueError):
        validate_diagnosis(value, state)


def test_diagnostics_capture_http400_without_provider_content_or_secrets():
    secret = "test-marker-" + secrets.token_hex(16)
    response = httpx2.Response(
        400,
        json={
            "error": {
                "code": "json_validate_failed",
                "message": secret,
                "reasoning": secret,
                "failed_generation": json.dumps({secret: secret}),
            }
        },
        headers={"x-request-id": "req_12345678", "authorization": secret},
    )
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(adapter(response).generate("diagnosis", {}, StrictDiagnosis))
    result = caught.value.diagnostic
    assert caught.value.code == "MODEL_HTTP_ERROR"
    assert result["category"] == "provider_schema_enforcement"
    assert result["failed_generation"]["category"] == "schema_validation"
    assert result["input_tokens"] is None
    assert secret not in json.dumps(result)


def test_length_completion_distinct_from_truncated_json_with_stop():
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(adapter(envelope("{", "length")).generate("diagnosis", {}, StrictDiagnosis))
    assert caught.value.diagnostic["category"] == "output_token_exhaustion"
    assert caught.value.diagnostic["output_tokens"] == 32


@pytest.mark.parametrize("kind", ["timeout", "connection"])
def test_transport_failures_preserve_sanitized_category(kind):
    def fail(_):
        raise (httpx2.ReadTimeout if kind == "timeout" else httpx2.ConnectError)("private")

    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        transport=httpx2.MockTransport(fail),
        request_interval_seconds=0,
    )
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(subject.generate("diagnosis", {}, StrictDiagnosis))
    assert caught.value.diagnostic["category"] == (
        "transport_timeout" if kind == "timeout" else "transport_error"
    )
    assert "private" not in json.dumps(caught.value.diagnostic)


def test_success_metadata_is_not_a_factual_accuracy_measure():
    state, value = packet()
    result = asyncio.run(
        adapter(envelope(json.dumps(value))).generate(
            "diagnosis",
            {"observations": [o.model_dump(mode="json") for o in state.observations]},
            StrictDiagnosis,
        )
    )
    assert result.diagnostic["outcome"] == "accepted_schema"
    assert result.diagnostic["reasoning_tokens"] == 10
    assert result.diagnostic["finish_reason"] == "stop"
    validate_diagnosis(result.value, state)


def test_failed_generation_is_parsed_only_in_memory_and_not_accepted():
    diagnostic = ModelDiagnostic()
    diagnostic.inspect_failed_generation({"error": {"failed_generation": "{"}}, StrictDiagnosis)
    assert diagnostic.failed_generation["category"] == "response_parsing"
    assert "failed_generation" not in diagnostic.failed_generation


def test_schema_incomplete_fixture_is_rejected_by_pydantic():
    _, value = packet()
    del value["recommendation"]["root_cause"]["explanation"]
    with pytest.raises(ValidationError):
        StrictDiagnosis.model_validate(value)


@pytest.mark.parametrize("mutation", ["approval_default", "action_default", "coerced_number"])
def test_adapter_must_enforce_the_wire_contract_even_if_pydantic_has_safe_defaults(mutation):
    state, value = packet()
    if mutation == "approval_default":
        del value["recommendation"]["proposed_remediation"]["human_approval_required"]
    elif mutation == "action_default":
        del value["recommendation"]["automatic_action_executed"]
    else:
        value["assessment"]["confidence"] = "0.8"
    assert list(Draft202012Validator(wire(state)).iter_errors(value))
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(
            adapter(envelope(json.dumps(value))).generate(
                "diagnosis",
                {},
                StrictDiagnosis,
            )
        )
    assert caught.value.diagnostic["category"] == "schema_validation"


@pytest.mark.parametrize(
    "schema,value",
    [
        (BasicJSON, {"status": "ready"}),
        (MinimalDiagnosis, {"root_cause": None, "uncertainty": ["Insufficient evidence."]}),
    ],
)
def test_isolation_schemas_are_satisfiable(schema, value):
    Draft202012Validator.check_schema(strict_schema(schema))
    Draft202012Validator(strict_schema(schema)).validate(value)


def test_plan_only_command_cannot_load_credentials_or_call_network(monkeypatch, capsys):
    import scripts.diagnose_stage9d as subject

    monkeypatch.setattr("sys.argv", ["stage9d"])
    monkeypatch.setattr(subject, "load_key", lambda: pytest.fail("Credential read"))
    monkeypatch.setattr(subject, "live", lambda *_: pytest.fail("Network request"))
    assert main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan == PLAN
    assert sum(plan["phase_requests"].values()) == 19
    assert plan["worst_case_list_price_estimate_usd"] < plan["maximum_reserved_usd"]


class ProbeFixture:
    """Explicit deterministic output, never an actual model or genuine MCP client."""

    def __init__(self, value):
        self.value, self.requests, self.bodies = value, [], []

    async def call(self, body, phase):
        self.bodies.append(body)
        assert not (body.get("tools") and body.get("response_format"))
        if body.get("tools"):
            return {
                "tool_calls": [
                    {
                        "id": "call_fixture_9d",
                        "type": "function",
                        "function": {
                            "name": "get_service_health",
                            "arguments": '{"service_name":"checkout-service"}',
                        },
                    }
                ]
            }
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True
        name = schema["name"]
        value = (
            {"status": "ready"}
            if name == "BasicJSON"
            else (
                {"root_cause": None, "uncertainty": ["Isolation only."]}
                if name == "MinimalDiagnosis"
                else self.value
            )
        )
        Draft202012Validator(schema["schema"]).validate(value)
        return {"content": json.dumps(value)}


def test_four_probes_keep_actual_tool_pair_and_unique_evidence_registry():
    from uuid import uuid4

    state, value = packet()
    budget = ProbeFixture(value)

    class HealthFixture:
        async def call(self, name, arguments):
            assert name == "get_service_health"
            assert arguments == {"service_name": "checkout-service"}
            return {
                "ok": True,
                "request_id": str(uuid4()),
                "data": {
                    "service_name": "checkout-service",
                    "status": "degraded",
                    "evidence": "latest_metric_window",
                    "observed_at": NOW,
                    "active_fault": None,
                    "metric": metric(),
                },
                "error": None,
            }

    before = state.model_dump_json()
    rows = asyncio.run(isolated_probes(budget, HealthFixture(), state))
    assert all(r["passed"] for r in rows), rows
    assert len(budget.bodies) == 5
    assert state.model_dump_json() == before
    messages = budget.bodies[-1]["messages"]
    assert messages[-3]["tool_calls"][0]["id"] == messages[-2]["tool_call_id"]
    result = json.loads(messages[-2]["content"])
    refs = [
        o["id"] for o in json.loads(messages[-1]["content"])["untrusted_evidence"]["observations"]
    ]
    assert result["observation"]["id"] == refs[-1] == "e006"
    assert len(set(refs)) == 6
    assert full_messages(state) == budget.bodies[2]["messages"]


def test_probe_c_distinguishes_schema_validity_from_failed_grounding():
    state, value = packet()
    value["recommendation"]["root_cause"]["confidence"] = 0.1
    row = asyncio.run(
        structured(ProbeFixture(value), "C", StrictDiagnosis, full_messages(state), state)
    )
    assert row["schema_valid"] and not row["passed"]
    assert row["failure_stage"] == "evidence_validation"


def test_probe_http_diagnostics_retain_only_safe_failure_metadata(tmp_path):
    from pydantic import SecretStr

    budget = DiagnosticBudget(tmp_path, SecretStr("synthetic-key"))
    body = {
        "model": MODELS[1],
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 1600,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "StrictDiagnosis",
                "strict": True,
                "schema": strict_schema(StrictDiagnosis),
            },
        },
    }
    response = httpx2.Response(
        400,
        json={
            "error": {
                "code": "json_validate_failed",
                "failed_generation": "{",
                "message": "private-message",
            }
        },
        headers={"x-request-id": "req_12345678"},
    )
    actual = httpx2.MockTransport(lambda _: response)
    asyncio.run(
        budget.exchange(httpx2.Request("POST", BASE + "/chat/completions"), body, "probe:C", actual)
    )
    recorded = json.loads((tmp_path / "requests.json").read_text())
    trace = recorded[0]["diagnostic"]
    assert trace["category"] == "provider_schema_enforcement"
    assert trace["failed_generation"]["category"] == "response_parsing"
    assert trace["request_id"] == "req_12345678"
    assert "private-message" not in json.dumps(recorded)


def test_workflow_cancellation_records_timeout_without_turning_into_success(caplog):
    import logging

    async def slow(_):
        await asyncio.sleep(10)

    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        transport=httpx2.MockTransport(slow),
        request_interval_seconds=0,
    )

    async def execute():
        async with asyncio.timeout(0.01):
            await subject.generate("diagnosis", {}, StrictDiagnosis)

    with caplog.at_level(logging.INFO), pytest.raises(TimeoutError):
        asyncio.run(execute())
    event = next(r.event for r in caplog.records if r.getMessage() == "model_diagnostic")
    assert event["category"] == "timeout_or_cancellation"
    assert event["outcome"] == "cancelled"
    assert event["timings_ms"]["total"] >= 0


def test_c_reproduces_the_historical_9c_request_without_changing_schema_or_prompt():
    from uuid import uuid4

    from opspilot.agent.schemas import InvestigationState, RunRequest
    from scripts.compare_groq_models import ROOT, digest

    folder = ROOT / "evaluations/reports/stage9c/20261118T112439Z-f2fef0"
    previous = json.loads((folder / "shared-probe-packet.json").read_text())
    request = RunRequest.model_validate(previous["request"])
    state = InvestigationState(
        request=request,
        incident_id=request.incident_id,
        run_id=uuid4(),
        goal=request.goal,
        mode="real",
        provider="groq",
        model=MODELS[1],
        observations=previous["observations"],
        evidence_references=[o["id"] for o in previous["observations"]],
    )
    requests = json.loads((folder / "requests.json").read_text())
    historical = requests[-1]
    assert historical["provider_error_code"] == "json_validate_failed"
    assert digest(full_messages(state)) == historical["prompt_sha256"]
    assert (
        digest(
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "StrictDiagnosis",
                    "strict": True,
                    "schema": wire(state),
                },
            }
        )
        == historical["schema_sha256"]
    )


def test_provider_rejection_cannot_be_accepted_even_when_failed_generation_is_valid():
    _, value = packet()
    response = httpx2.Response(
        400,
        json={
            "error": {
                "code": "json_validate_failed",
                "failed_generation": json.dumps(value),
            }
        },
    )
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(adapter(response).generate("diagnosis", {}, StrictDiagnosis))
    assert caught.value.diagnostic["category"] == "provider_schema_enforcement"
    assert caught.value.diagnostic["failed_generation"]["category"] == "schema_valid"


def test_diagnosis_probe_cannot_accept_duplicate_root_cause_references():
    state, value = packet()
    value["recommendation"]["root_cause"]["evidence_refs"].append(
        value["recommendation"]["root_cause"]["evidence_refs"][0]
    )
    with pytest.raises(ValueError):
        validate_diagnosis(value, state)


@pytest.mark.parametrize(
    "field,number", [("human_approval_required", 1), ("automatic_action_executed", 0)]
)
def test_safety_literals_must_be_json_booleans_not_numeric_equivalents(field, number):
    state, value = packet()
    target = value["recommendation"]
    if field == "human_approval_required":
        target = target["proposed_remediation"]
    target[field] = number
    assert list(Draft202012Validator(wire(state)).iter_errors(value))
    with pytest.raises(ModelFailure):
        asyncio.run(adapter(envelope(json.dumps(value))).generate("diagnosis", {}, StrictDiagnosis))


def test_probe_budget_denial_cannot_be_attributed_to_previous_provider_response():
    state, value = packet()

    class Denied(ProbeFixture):
        async def call(self, *_):
            raise ModelFailure("REQUEST_BUDGET_EXHAUSTED")

    budget = Denied(value)
    budget.requests.append({"diagnostic": {"category": "schema_valid"}})
    row = asyncio.run(structured(budget, "C", StrictDiagnosis, full_messages(state), state))
    assert not row["passed"] and row["failure_stage"] == "request_policy"


def test_empty_provider_failed_generation_is_not_proof_of_malformed_model_output():
    diagnostic = ModelDiagnostic()
    diagnostic.inspect_failed_generation({"error": {"failed_generation": ""}}, StrictDiagnosis)
    assert diagnostic.failed_generation == {
        "chars": 0,
        "category": "empty_provider_diagnostic",
        "validation_errors": [],
    }


def test_live_rate_limit_failure_has_a_separate_category_and_is_not_retried():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx2.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    subject = HTTPDecisionModel(
        "groq",
        MODELS[1],
        BASE,
        "synthetic-key",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(respond),
    )
    with pytest.raises(ModelFailure) as caught:
        asyncio.run(subject.generate("diagnosis", {}, StrictDiagnosis))
    assert caught.value.code == "MODEL_RATE_LIMITED"
    assert caught.value.diagnostic["category"] == "provider_rate_limit"
    assert len(calls) == 1
