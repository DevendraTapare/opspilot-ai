"""Offline controls: no provider inference, no automatic remediation."""

import json

import pytest
from test_agent import FixtureMCP, request, run

from opspilot.agent.budgets import OUTPUT_RESERVATION, estimate_input_tokens
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import Triage
from opspilot.agent.workflow import Investigation


class NeverConclude(FixtureDecisionModel):
    async def generate(self, stage, context, schema):
        reply = await super().generate(stage, context, schema)
        if stage == "evidence_assessment":
            reply.value.decision = "investigate"
        return reply


def test_round_limit_stops_investigation_without_forcing_diagnosis():
    state = run(NeverConclude())
    assert state.run_status == "budget_exhausted"
    assert state.errors[-1].code == "INVESTIGATION_ROUND_LIMIT"
    assert state.usage.model_calls == 9
    assert len(state.observations) == 5
    assert state.proposed_remediation is None and state.candidate_root_cause is None
    assert not state.recommendation.automatic_action_executed


def test_finalization_reserve_stops_before_an_unfinishable_extra_round():
    state = run(NeverConclude(), max_model_calls=8, max_investigation_rounds=10)
    assert state.errors[-1].code == "FINALIZATION_RESERVE_EXHAUSTED"
    assert state.usage.model_calls == 5
    assert state.run_status == "budget_exhausted"


@pytest.mark.parametrize(
    "limits,code",
    [
        ({"max_estimated_tokens": 1}, "TOKEN_ESTIMATE_EXHAUSTED"),
        ({"max_prompt_estimated_tokens": 1}, "PROMPT_ESTIMATE_EXHAUSTED"),
    ],
)
def test_token_admission_occurs_before_model_dispatch(limits, code):
    class Forbidden(FixtureDecisionModel):
        async def generate(self, *args):
            pytest.fail("No model dispatch after token admission rejection")

    state = run(Forbidden(), **limits)
    assert state.errors[-1].code == code
    assert state.run_status == "budget_exhausted"
    assert state.usage.model_calls == state.usage.estimated_token_reservation == 0
    assert state.recommendation.root_cause is None


def test_uncertain_failure_keeps_token_reservation():
    class Failed(FixtureDecisionModel):
        async def generate(self, *args):
            raise ModelFailure("MODEL_TIMEOUT")

    state = run(Failed())
    assert state.usage.estimated_token_reservation > OUTPUT_RESERVATION
    assert state.usage.estimated_token_reservation == (
        state.usage.estimated_input_tokens + OUTPUT_RESERVATION
    )
    assert not state.usage.usage_complete
    assert state.proposed_remediation is None


def test_cumulative_estimate_stops_second_dispatch_and_keeps_first_reservation():
    class Estimated(FixtureDecisionModel):
        def estimate_request(self, *args):
            return 100

    state = run(Estimated(), max_estimated_tokens=3399)
    assert state.run_status == "budget_exhausted"
    assert state.errors[-1].code == "TOKEN_ESTIMATE_EXHAUSTED"
    assert state.usage.model_calls == 1
    assert state.usage.estimated_token_reservation == 1700
    assert len(state.observations) == 1
    assert state.recommendation.root_cause is None


def test_compaction_keeps_exact_observations_and_validates_hidden_bindings():
    state = run()
    from opspilot.agent.schemas import DiagnosticStep, ModelToolCall

    state.tool_call_history[1].model_call = ModelToolCall(
        id="synthetic_call",
        arguments=DiagnosticStep(
            tool_name="get_service_metrics",
            service_name=state.request.service_name,
            rationale="Synthetic binding for offline validation.",
        ),
    )
    context = Investigation(None, None, state.request)._context(state)
    model = HTTPDecisionModel("openai-compatible", "mock", "http://localhost:1234/v1")

    body, _ = model.prepare_request("investigation_planning", context, DiagnosticStep)
    wire = json.loads(body["messages"][-1]["content"])["untrusted_investigation_context"]
    assert wire["observations"] == context["observations"]
    assert wire["evidence_registry"] == context["evidence_registry"]
    assert "hypotheses" not in wire["assessment"]
    assert wire["hypotheses"] == context["assessment"]["hypotheses"]
    assert "tool_history" not in wire
    for message in body["messages"]:
        if message["role"] == "tool":
            result = json.loads(message["content"])
            assert "observation" not in result
            observation = next(o for o in wire["observations"] if o["id"] == result["evidence_ref"])
            assert result["request_id"] == observation["request_id"]
    assert model.estimate_request("investigation_planning", context, DiagnosticStep) == (
        estimate_input_tokens(body)
    )
    context["hypotheses"] = []
    divergent, _ = model.prepare_request("investigation_planning", context, DiagnosticStep)
    divergent_context = json.loads(divergent["messages"][-1]["content"])[
        "untrusted_investigation_context"
    ]
    assert divergent_context["assessment"]["hypotheses"] == context["assessment"]["hypotheses"]
    context["tool_history"][1]["request_id"] = "substituted"
    with pytest.raises(ValueError, match="binding"):
        model.prepare_request("investigation_planning", context, DiagnosticStep)


def test_duplicate_exact_diagnostic_is_blocked_before_mcp():
    class Duplicate(FixtureDecisionModel):
        async def generate(self, stage, context, schema):
            reply = await super().generate(stage, context, schema)
            if stage == "investigation_planning":
                reply.value.tool_name = "get_service_metrics"
            return reply

    mcp = FixtureMCP()
    state = run(Duplicate(), mcp)
    assert state.run_status == "abstained"
    assert [name for name, _ in mcp.calls].count("get_service_metrics") == 1
    assert state.proposed_remediation is None


def test_estimator_is_utf8_and_reserves_framing_not_reported_usage():
    assert estimate_input_tokens({"v": "é"}) > len(json.dumps({"v": "é"}, ensure_ascii=False))
    state = run()
    assert state.run_status == "completed"
    assert state.usage.input_tokens == state.usage.output_tokens == 0
    assert state.usage.estimated_token_reservation > 0
    assert not state.usage.usage_complete


def test_explicit_abstention_is_reachable_before_round_limit():
    state = run(mcp=FixtureMCP(degraded=False))
    assert state.run_status == "abstained"
    assert state.proposed_remediation is None


def test_model_request_estimate_is_pure_and_never_reads_a_key_or_network():
    model = HTTPDecisionModel("openai-compatible", "mock", "http://localhost:1234/v1")
    context = Investigation(None, None, request())._context
    # Direct empty context is supported for isolated schema probes, without a request.
    assert model.estimate_request("triage", {}, Triage) > 512
    assert model.last_request_started == 0
    assert callable(context)


def test_historical_analysis_does_not_fabricate_rejected_request_usage():
    from scripts.replay_stage9e1 import historical_rows

    rows = historical_rows()
    assert len(rows) == 12
    assert rows[-1]["reported_input_tokens"] is None
    assert rows[-1]["reported_output_tokens"] is None
    assert rows[-1]["estimated_input_tokens"] == 26813
    assert rows[-1]["tool_selected"] is None
    assert rows[-2]["decision"] == "investigate"
    assert rows[9]["semantic_repetition"] == "same metric sample as e002"
    assert rows[4]["corroboration_inputs_available"]


@pytest.mark.parametrize("status", ["budget_exhausted", "abstained", "failed"])
def test_incomplete_status_cannot_enter_approval_even_with_a_leftover_proposal(status):
    from opspilot.durable.contracts import ExecutionError
    from opspilot.durable.repository import Repository

    state = run().model_copy(update={"run_status": status})
    # Deliberately retain a fixture proposal: the independent durable gate must
    # reject the status before touching any database or creating an approval.
    with pytest.raises(ExecutionError) as error:
        Repository(object()).submit(state)
    assert error.value.code == "UNSUPPORTED_RECOMMENDATION"
