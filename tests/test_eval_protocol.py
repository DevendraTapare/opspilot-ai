"""Controller/agent separation and distributed spans over actual MCP, never a fake protocol."""

import json

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evaluations.runners.dataset import load
from evaluations.runners.environment import Environment
from evaluations.runners.subjects import baseline, structured
from opspilot import observability
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.mcp import connect


@pytest.mark.anyio
async def test_controller_isolation_projection_and_mcp_trace_parenting(engine, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("evaluation controller requires PostgreSQL")
    monkeypatch.setattr(observability, "_provider", None)
    exporter = InMemorySpanExporter()
    observability.configure_tracing(exporter=exporter)
    contexts = []

    class CaptureFixture(FixtureDecisionModel):
        async def generate(self, stage, context, schema):
            contexts.append(json.dumps(context))
            return await super().generate(stage, context, schema)

    with Environment(engine.url.render_as_string(hide_password=False)).start() as environment:
        public = environment.prepare(load("calibration")[0])
        with observability.span("test.protocol") as parent:
            async with connect(environment.url, environment.token) as mcp:
                result = await structured(public, mcp, CaptureFixture())
        assert result.status == "diagnosed"
        assert contexts
        assert all(
            word not in text
            for text in contexts
            for word in [
                '"fault_id"',
                '"scenario_id"',
                "worker-saturation",
                '"expected_mechanism"',
                '"family"',
            ]
        )
        spans = exporter.get_finished_spans()
        server = [s for s in spans if s.name == "execute_tool mcp-server"]
        backend = [s for s in spans if s.name == "execute_tool authorization-backend"]
        assert len(server) == len(backend) == 6
        assert all(
            s.context.trace_id == parent.get_span_context().trace_id for s in server + backend
        )
        assert {s.parent.span_id for s in backend} <= {s.context.span_id for s in server}
        healthy = next(c for c in load("calibration") if c.family == "no_fault")
        public = environment.prepare(healthy)
        async with connect(environment.url, environment.token) as mcp:
            assert (await baseline(public, mcp)).status == "abstained"
