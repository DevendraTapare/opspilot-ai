"""Real HTTP integration against the dedicated Compose API, opt in via environment."""

import os

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.live
SERVICES = ["checkout-service", "payment-service", "inventory-service"]


@pytest.fixture
def live_client():
    endpoint = os.environ.get("OPSPILOT_LIVE_API_URL")
    token = os.environ.get("OPSPILOT_CONTROL_TOKEN")
    if not endpoint or not token:
        pytest.skip("Running API URL and control token not configured")
    if endpoint not in {"http://api:8000", "http://127.0.0.1:8084", "http://localhost:8084"}:
        pytest.fail("Live tests require the dedicated local OpsPilot API")
    with httpx.Client(
        base_url=endpoint, headers={"Authorization": f"Bearer {token}"}, timeout=20
    ) as client:
        yield client


def test_live_readiness_auth_and_openapi(live_client):
    assert live_client.get("/health/ready").status_code == 200
    assert len(live_client.get("/api/v1/services").json()) == 3
    assert live_client.get("/openapi.json").status_code == 200
    response = live_client.post(
        "/api/v1/fixtures/reset",
        json={"services": SERVICES},
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401


def test_live_fault_dependency_incident_and_selected_reset(live_client):
    reset = {"services": SERVICES, "seed": 42}
    assert live_client.post("/api/v1/fixtures/reset", json=reset).status_code == 200
    try:
        baseline = live_client.post("/api/v1/simulator/checkout-service/workloads", json={}).json()
        assert all(result["status_code"] == 200 for result in baseline["results"])
        inventory = live_client.get("/api/v1/services/inventory-service/metrics").json()
        fault = live_client.post(
            "/api/v1/faults",
            json={
                "service_name": "payment-service",
                "scenario_id": "payment-unavailable",
            },
        )
        assert fault.status_code == 201
        failure = live_client.post("/api/v1/simulator/checkout-service/request")
        assert failure.status_code == 502
        incidents = live_client.get("/api/v1/incidents?status=open").json()
        assert {i["service_name"] for i in incidents} == {"checkout-service", "payment-service"}
        for incident in incidents:
            incident_id = incident["id"]
            assert live_client.get(f"/api/v1/incidents/{incident_id}/metrics").json()
            assert live_client.get(f"/api/v1/incidents/{incident_id}/logs").json()
        selected = live_client.post(
            "/api/v1/fixtures/reset",
            json={
                "services": ["payment-service", "checkout-service"],
                "seed": 42,
            },
        )
        assert selected.status_code == 200
        assert live_client.get("/api/v1/services/inventory-service/metrics").json() == inventory
        assert live_client.post("/api/v1/simulator/checkout-service/request").status_code == 200
    finally:
        assert live_client.post("/api/v1/fixtures/reset", json=reset).status_code == 200
