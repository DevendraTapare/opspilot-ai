"""Deterministic adversarial fixtures; none of these tests performs LLM inference."""

import asyncio

import pytest
from test_agent import INCIDENT_ID, FixtureMCP, metric

from evaluations.runners.contracts import Choice, PublicCase
from evaluations.runners.subjects import baseline, llm_tools, read
from opspilot.agent.providers import ModelReply
from opspilot.agent.schemas import DiagnosticStep

PUBLIC = PublicCase(incident_id=INCIDENT_ID, service_name="checkout-service")


class SubstitutedMetrics(FixtureMCP):
    async def call(self, name, arguments):
        value = await super().call(name, arguments)
        if name == "get_service_metrics":
            value["data"]["items"][0]["service_name"] = "payment-service"
        return value


def test_evaluation_shared_read_rejects_service_substitution():
    with pytest.raises(ValueError, match="response page service mismatch"):
        asyncio.run(read(SubstitutedMetrics(), "get_service_metrics", PUBLIC))


def test_evaluation_unstructured_arm_rejects_service_substitution():
    class FixedChoice:
        async def generate(self, stage, context, schema):
            return ModelReply(
                Choice(
                    decision="investigate",
                    step=DiagnosticStep(
                        tool_name="get_service_metrics",
                        service_name="checkout-service",
                        rationale="Read quantitative observations.",
                    ),
                    service_name=None,
                    mechanism=None,
                    evidence_refs=[],
                    explanation="Deterministic test input, not model reasoning.",
                )
            )

    with pytest.raises(ValueError, match="response page service mismatch"):
        asyncio.run(llm_tools(PUBLIC, SubstitutedMetrics(), FixedChoice()))


class CompetingSignals(FixtureMCP):
    def __init__(self, local_pressure):
        super().__init__()
        self.local_pressure = local_pressure

    async def call(self, name, arguments):
        value = await super().call(name, arguments)
        if name == "get_service_metrics":
            value["data"]["items"][0]["worker_utilization"] = 1 if self.local_pressure else 0.5
        if name == "get_dependency_status":
            payment = value["data"]["dependencies"][0]
            payment["metric"] = metric("payment-service", True)
            payment["metric"]["worker_utilization"] = 0.5
            payment["status"] = "degraded"
        return value


@pytest.mark.parametrize("local_pressure", [True, False])
def test_baseline_does_not_discard_competing_local_resource_evidence(local_pressure):
    result = asyncio.run(baseline(PUBLIC, CompetingSignals(local_pressure)))
    if local_pressure:
        assert result.status == "abstained"
    else:
        assert result.status == "diagnosed"
        assert result.service == "payment-service"
        assert result.mechanism == "dependency_unavailable"
