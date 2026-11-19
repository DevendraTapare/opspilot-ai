"""Real database-backed web identity, CSRF, projection and permission checks."""

import getpass
import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.dashboard.api import create_dashboard
from opspilot.dashboard.config import DashboardSettings
from opspilot.dashboard.security import session_digest
from opspilot.durable.cli import RunnerSettings
from opspilot.durable.operator import OperatorSettings
from opspilot.models import DashboardSession

KEY = "dashboard-test-service-" + "k" * 40
TOKEN = "dashboard-synthetic-human-" + "h" * 40
HEADERS = {"x-dashboard-key": KEY, "origin": "http://127.0.0.1:3000"}


@pytest.fixture
def dashboard(engine):
    registry = json.dumps(
        [
            {
                "subject": "dashboard-test-human",
                "os_user": getpass.getuser(),
                "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "services": ["checkout-service"],
                "actions": ["restart_simulated_worker"],
            }
        ]
    )
    app = create_dashboard(
        DashboardSettings(
            service_key=KEY, reader_token="r" * 64, control_token="c" * 64, _env_file=None
        ),
        RunnerSettings(database_url="unused", mcp_token="e" * 64, _env_file=None),
        OperatorSettings(
            database_url="unused", approval_key="s" * 64, operators=registry, _env_file=None
        ),
        engine,
        engine,
    )
    with TestClient(app) as client:
        client.headers.update(HEADERS)
        yield client


def test_requires_bff_identity(dashboard):
    assert dashboard.get("/meta", headers={"x-dashboard-key": "wrong"}).status_code == 401


def test_session_is_human_authenticated_revocable_and_http_only(dashboard, engine):
    assert dashboard.get("/meta").json()["session"] is None
    response = dashboard.post("/session", json={"credential": TOKEN})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    token = dashboard.cookies.get("opspilot_session")
    assert len(token) == 64 and TOKEN not in response.text
    with Session(engine) as session:
        row = session.scalar(select(DashboardSession))
        security = dashboard.app.router.dependencies[0].dependency.__self__
        assert row.token_sha256 == session_digest(security.principals()[0], token)
    assert dashboard.get("/meta").json()["session"]["subject"] == "dashboard-test-human"
    assert dashboard.request("DELETE", "/session", json={}).status_code == 200
    dashboard.cookies.set("opspilot_session", token)
    assert dashboard.get("/meta").json()["session"] is None


def test_no_unauthenticated_mutations(dashboard):
    for path, body in [
        ("/simulation", {"service_name": "checkout-service", "scenario_id": "worker-saturation"}),
        ("/runs", {"incident_id": str(uuid4()), "request_id": str(uuid4()), "mode": "fixture"}),
        (f"/approvals/{uuid4()}/decision", {"decision": "approve", "fingerprint": "a" * 64}),
        (f"/runs/{uuid4()}/resume", {}),
    ]:
        assert dashboard.post(path, json=body).status_code == 401


def test_csrf_and_oversized_credentials_are_rejected_without_echo(dashboard):
    response = dashboard.post(
        "/session", json={"credential": TOKEN}, headers={"origin": "https://untrusted.invalid"}
    )
    assert response.status_code == 403
    secret = "do-not-echo-" * 40
    response = dashboard.post("/session", json={"credential": secret})
    assert response.status_code == 422 and secret not in response.text
    assert dashboard.post("/session", content="x" * 17000).status_code == 413


def test_scoped_human_cannot_reset_other_service(dashboard):
    dashboard.post("/session", json={"credential": TOKEN})
    response = dashboard.post(
        "/simulation", json={"service_name": "payment-service", "scenario_id": "worker-saturation"}
    )
    assert response.status_code == 403


def test_no_client_selected_approver_or_arbitrary_command(dashboard):
    dashboard.post("/session", json={"credential": TOKEN})
    response = dashboard.post(
        f"/approvals/{uuid4()}/decision",
        json={"decision": "approve", "fingerprint": "a" * 64, "approved_by": "admin"},
    )
    assert response.status_code == 422
    assert dashboard.post("/tools/execute_shell", json={"command": "whoami"}).status_code == 404


def test_real_mode_does_not_fall_back(dashboard, monkeypatch):
    monkeypatch.setattr("opspilot.dashboard.api.real_model_available", lambda: False)
    dashboard.post("/session", json={"credential": TOKEN})
    response = dashboard.post(
        "/runs", json={"incident_id": str(uuid4()), "request_id": str(uuid4()), "mode": "real"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_MODEL_NOT_CONFIGURED"


def test_live_views_and_inventory_are_real_bounded_and_nonprivileged(dashboard):
    response = dashboard.get("/overview")
    assert response.status_code == 200
    assert len(response.json()["services"]) == 3
    assert not response.json()["runs"]
    assert "active_fault" not in response.text
    assert len(dashboard.get("/architecture").json()["tools"]) == 12
    assert dashboard.get("/health/ready").json()["migration"] == "0004_dashboard"
    assert dashboard.get("/incidents/not-a-uuid").status_code == 422


def test_evaluations_expose_recorded_aggregates_without_heldout_answers(dashboard):
    result = dashboard.get("/evaluations")
    assert result.status_code == 200
    value = result.json()
    assert value["historical_stage"] == 5
    held = value["reports"]["held-out"]
    assert "trials" not in held and "frozen_plan" not in held
    assert held["metrics"]["llm"]["attempted"] == 0
    assert held["metrics"]["baseline"]["attempted"] == 40
