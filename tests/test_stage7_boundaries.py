"""Adversarial regressions: synthetic credentials, bounded payloads, no real model."""

import asyncio
import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import SecretStr
from test_agent import FixtureMCP, run
from test_dashboard import TOKEN, dashboard  # noqa: F401

from opspilot.gateway.authorizer import BodyLimit


def test_rotated_human_credential_invalidates_existing_sessions(dashboard):  # noqa: F811
    assert dashboard.post("/session", json={"credential": TOKEN}).status_code == 200
    security = dashboard.app.router.dependencies[0].dependency.__self__
    registry = json.loads(security.operator.operators.get_secret_value())
    registry[0]["token_sha256"] = hashlib.sha256(
        ("replacement-human-" + "x" * 40).encode()
    ).hexdigest()
    security.operator.operators = SecretStr(json.dumps(registry))
    assert dashboard.get("/meta").json()["session"] is None
    assert (
        dashboard.post(
            "/runs",
            json={"request_id": str(uuid4()), "incident_id": str(uuid4()), "mode": "fixture"},
        ).status_code
        == 401
    )


@pytest.mark.parametrize("mutation", ["service", "incident", "dependency"])
def test_substituted_tool_evidence_cannot_support_a_diagnosis(mutation):
    class Substitution(FixtureMCP):
        async def call(self, name, arguments):
            value = await super().call(name, arguments)
            if mutation == "incident" and name == "get_incident":
                value["data"]["incident"]["id"] = str(uuid4())
            if mutation == "service" and name == "get_service_metrics":
                value["data"]["items"][0]["service_name"] = "payment-service"
            if mutation == "dependency" and name == "get_dependency_status":
                value["data"]["dependencies"][0]["service_name"] = "checkout-service"
            return value

    result = run(mcp=Substitution())
    assert result.run_status != "completed"
    assert result.proposed_remediation is None
    assert any(e.code == "TOOL_RESPONSE_INVALID" for e in result.errors)


def test_slow_drip_has_an_absolute_body_deadline():
    async def exercise():
        emitted = []
        called = []

        async def app(scope, receive, send):
            called.append(True)

        async def receive():
            await asyncio.sleep(0.015)
            return {"type": "http.request", "body": b"x", "more_body": True}

        async def send(message):
            emitted.append(message)

        boundary = BodyLimit(app)
        boundary.timeout_seconds = 0.05
        try:
            await asyncio.wait_for(boundary({"type": "http"}, receive, send), 0.3)
        except TimeoutError:
            pytest.fail("Drip-fed body retained the request beyond the absolute deadline")
        assert not called
        assert emitted[0]["status"] == 408

    asyncio.run(exercise())
