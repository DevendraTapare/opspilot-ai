import math
import secrets
import time
from collections import Counter
from statistics import mean
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from opspilot.config import Settings
from opspilot.main import create_app
from opspilot.models import Base, Fault, MetricSummary, Service, SimulationLog

SERVICES = ["checkout-service", "payment-service", "inventory-service"]


def metric_for(run, service):
    return next(metric for metric in run["metrics"] if metric["service_name"] == service)


def test_health_baseline(client, workload):
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert {row["name"] for row in client.get("/api/v1/services").json()} == set(SERVICES)
    run = workload("checkout-service")
    assert all(row["status_code"] == 200 for row in run["results"])
    assert {row["service_name"] for row in run["metrics"]} == set(SERVICES)
    for metric in run["metrics"]:
        assert metric["errors"] == 0
        assert metric["requests"] == 12
        assert 0 < metric["p95_latency_ms"] < 100
    assert client.get("/api/v1/incidents").json() == []


@pytest.mark.parametrize(
    ("service", "scenario", "status", "code"),
    [
        ("checkout-service", "slow-checkout", 200, "ok"),
        ("payment-service", "payment-unavailable", 503, "payment_dependency_unavailable"),
        ("inventory-service", "inventory-db-exhaustion", 503, "database_pool_timeout"),
        ("checkout-service", "bad-config", 500, "invalid_checkout_configuration"),
    ],
)
def test_fault_effects(client, auth, activate, service, scenario, status, code):
    fault = activate(service, scenario)
    # Activation alone is not an observed incident.
    assert client.get("/api/v1/incidents").json() == []
    response = client.post(f"/api/v1/simulator/{service}/request", headers=auth)
    assert response.status_code == status
    result = response.json()["results"][0]
    assert result["code"] == code
    if scenario == "slow-checkout":
        assert result["latency_ms"] >= 550
    metric = metric_for(response.json(), service)
    assert metric["fault_id"] == fault["id"]
    if scenario == "inventory-db-exhaustion":
        assert metric["db_pool_utilization"] == 1
    incidents = client.get("/api/v1/incidents").json()
    # Inventory has a separate resource-exhaustion trigger, even for sub-300ms timeouts.
    assert len(incidents) == 1
    assert incidents[0]["scenario_id"] == scenario


def test_saturation_is_load_dependent(workload, activate):
    healthy = workload("payment-service", count=30, interval=0)
    activate("payment-service", "worker-saturation")
    saturated = workload("payment-service", count=30, interval=0)
    baseline = metric_for(healthy, "payment-service")
    faulty = metric_for(saturated, "payment-service")
    assert faulty["errors"] > baseline["errors"]
    assert faulty["worker_utilization"] > baseline["worker_utilization"]
    assert any(row["code"] == "worker_queue_timeout" for row in saturated["results"])


def test_metrics_are_exact_request_aggregates(client, workload, activate):
    activate("checkout-service", "slow-checkout")
    run = workload("checkout-service", count=30, interval=0)
    metric = metric_for(run, "checkout-service")
    results = run["results"]
    latency = sorted(row["latency_ms"] for row in results)
    errors = sum(row["status_code"] >= 400 for row in results)
    assert metric["errors"] == errors
    assert metric["error_rate"] == errors / len(results)
    assert metric["status_counts"] == dict(Counter(str(row["status_code"]) for row in results))
    assert metric["avg_latency_ms"] == round(mean(latency), 3)
    assert metric["p95_latency_ms"] == latency[math.ceil(0.95 * len(results)) - 1]
    assert metric["max_latency_ms"] == max(latency)
    logs = client.get("/api/v1/services/checkout-service/logs").json()
    assert len(logs) == len(results)
    assert sorted(row["latency_ms"] for row in logs) == latency


def test_dependency_failure_and_unrelated_service_isolation(client, workload, activate):
    before = workload("inventory-service")
    activate("payment-service", "payment-unavailable")
    run = workload("checkout-service")
    assert all(row["status_code"] == 502 for row in run["results"])
    assert {m["service_name"] for m in run["metrics"]} == {"checkout-service", "payment-service"}
    incidents = client.get("/api/v1/incidents?status=open").json()
    assert {i["service_name"] for i in incidents} == {"checkout-service", "payment-service"}
    assert client.get("/api/v1/services/inventory-service/metrics").json() == before["metrics"]
    after = workload("inventory-service")
    assert metric_for(after, "inventory-service")["errors"] == 0


@pytest.mark.parametrize(
    ("service", "scenario"),
    [
        ("checkout-service", "slow-checkout"),
        ("checkout-service", "bad-config"),
        ("inventory-service", "inventory-db-exhaustion"),
        ("payment-service", "worker-saturation"),
    ],
)
def test_direct_fault_does_not_modify_other_fixtures(client, workload, activate, service, scenario):
    untouched = {
        row["name"]: row for row in client.get("/api/v1/services").json() if row["name"] != service
    }
    activate(service, scenario)
    workload(service)
    after = {row["name"]: row for row in client.get("/api/v1/services").json()}
    # Checkout intentionally invokes its dependencies, advancing their cursors.
    for name, original in untouched.items():
        assert after[name]["seed"] == original["seed"]
        assert after[name]["generation"] == original["generation"]
        if service != "checkout-service" or scenario == "bad-config":
            assert after[name] == original
    faults = client.get("/api/v1/faults?active=true").json()
    assert [row["service_name"] for row in faults] == [service]


def test_incident_events_logs_recovery_and_deduplication(client, auth, activate, workload):
    fault = activate("payment-service", "payment-unavailable")
    workload("payment-service")
    workload("payment-service")
    incidents = client.get("/api/v1/incidents").json()
    assert len(incidents) == 1
    incident_id = incidents[0]["id"]
    detail = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert [event["kind"] for event in detail["events"]] == ["opened", "observation"]
    assert len(client.get(f"/api/v1/incidents/{incident_id}/metrics").json()) == 2
    logs = client.get(f"/api/v1/incidents/{incident_id}/logs").json()
    assert len(logs) == 24
    assert all(log["status_code"] == 503 for log in logs)
    url = f"/api/v1/faults/{fault['id']}/deactivate"
    assert client.post(url, headers=auth).status_code == 200
    # Deactivation is idempotent; recovery requires a healthy observation.
    assert client.post(url, headers=auth).status_code == 200
    assert client.get(f"/api/v1/incidents/{incident_id}").json()["status"] == "open"
    workload("payment-service")
    detail = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert detail["status"] == "resolved"
    assert detail["events"][-1]["kind"] == "recovered"


def test_selected_reset_repeatability_and_history(client, auth, activate, workload):
    payment_fault = activate("payment-service", "payment-unavailable")
    inventory_fault = activate("inventory-service", "inventory-db-exhaustion")
    workload("payment-service")
    workload("inventory-service")
    inventory_before = client.get("/api/v1/services/inventory-service/metrics").json()
    body = {"services": ["payment-service"], "seed": 137}
    first = client.post("/api/v1/fixtures/reset", headers=auth, json=body).json()
    assert first["deactivated_fault_ids"] == [payment_fault["id"]]
    assert len(first["resolved_incident_ids"]) == 1
    result_a = workload("payment-service")
    second = client.post("/api/v1/fixtures/reset", headers=auth, json=body).json()
    assert second["deactivated_fault_ids"] == []
    assert second["resolved_incident_ids"] == []
    result_b = workload("payment-service")
    assert result_a["results"] == result_b["results"]
    assert metric_for(result_a, "payment-service")["seed"] == 137
    assert client.get("/api/v1/services/inventory-service/metrics").json() == inventory_before
    assert client.get("/api/v1/faults?active=true").json()[0]["id"] == inventory_fault["id"]
    assert len(client.get("/api/v1/services/payment-service/metrics").json()) == 3


def test_bad_config_deployment_and_rollback(client, auth, activate, workload):
    fault = activate("checkout-service", "bad-config")
    workload("checkout-service")
    events = client.get("/api/v1/services/checkout-service/deployments").json()
    assert events[0]["fault_id"] == fault["id"]
    assert events[0]["config"] == {"tax_mode": "unsupported-v0"}
    client.post(f"/api/v1/faults/{fault['id']}/deactivate", headers=auth)
    assert workload("checkout-service")["results"][0]["status_code"] == 200
    events = client.get("/api/v1/services/checkout-service/deployments").json()
    assert events[-1]["kind"] == "simulated_config_rollback"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/api/v1/faults",
            {"service_name": "payment-service", "scenario_id": "payment-unavailable"},
        ),
        ("/api/v1/fixtures/reset", {"services": ["payment-service"]}),
        ("/api/v1/simulator/payment-service/workloads", {"count": 1}),
        ("/api/v1/simulator/payment-service/request", None),
        (f"/api/v1/faults/{uuid4()}/deactivate", None),
    ],
)
def test_control_authentication(client, path, body):
    for headers in ({}, {"Authorization": "Bearer incorrect"}):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/v1/faults").json() == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/faults", {"service_name": "inventory-service", "scenario_id": "slow-checkout"}),
        ("/api/v1/faults", {"service_name": "production", "scenario_id": "bad-config"}),
        ("/api/v1/faults", {"service_name": "payment-service", "scenario_id": "unknown"}),
        ("/api/v1/fixtures/reset", {}),
        ("/api/v1/fixtures/reset", {"services": []}),
        ("/api/v1/fixtures/reset", {"services": ["all"]}),
        ("/api/v1/fixtures/reset", {"services": ["payment-service", "payment-service"]}),
        ("/api/v1/fixtures/reset", {"services": ["payment-service"], "seed": -1}),
        ("/api/v1/fixtures/reset", {"services": ["payment-service"], "seed": True}),
        ("/api/v1/fixtures/reset", {"services": ["payment-service"], "delete_history": True}),
        ("/api/v1/simulator/payment-service/workloads", {"count": 51}),
        ("/api/v1/simulator/payment-service/workloads", {"count": "12"}),
        ("/api/v1/simulator/payment-service/workloads", {"arrival_interval_ms": 101}),
    ],
)
def test_validation(client, auth, path, body):
    assert client.post(path, headers=auth, json=body).status_code == 422


def test_conflicts_not_found_and_pagination(client, auth, activate, workload):
    activate("payment-service", "payment-unavailable")
    conflict = client.post(
        "/api/v1/faults",
        headers=auth,
        json={
            "service_name": "payment-service",
            "scenario_id": "worker-saturation",
        },
    )
    assert conflict.status_code == 409
    workload("payment-service")
    assert len(client.get("/api/v1/services/payment-service/logs?limit=3&offset=2").json()) == 3
    assert client.get("/api/v1/incidents?limit=501").status_code == 422
    assert client.get("/api/v1/incidents?status=unknown").status_code == 422
    assert client.get("/api/v1/incidents/not-a-uuid").status_code == 422
    for suffix in ("", "/metrics", "/logs"):
        assert client.get(f"/api/v1/incidents/{uuid4()}{suffix}").status_code == 404
    assert client.post(f"/api/v1/faults/{uuid4()}/deactivate", headers=auth).status_code == 404


def test_persistence_after_engine_reconnect(engine, client, activate, workload):
    fault = activate("inventory-service", "inventory-db-exhaustion")
    workload("inventory-service")
    incident = client.get("/api/v1/incidents").json()[0]
    engine.dispose()
    app = create_app(
        Settings(control_token=secrets.token_hex(32), _env_file=None),
        engine=engine,
    )
    with TestClient(app) as restarted:
        assert restarted.get("/api/v1/faults").json()[0]["id"] == fault["id"]
        detail = restarted.get(f"/api/v1/incidents/{incident['id']}").json()
        assert detail["status"] == "open"
        assert len(detail["events"]) == 1
        assert len(restarted.get(f"/api/v1/incidents/{incident['id']}/metrics").json()) == 1
        assert len(restarted.get(f"/api/v1/incidents/{incident['id']}/logs").json()) == 12


def test_failed_transaction_rolls_back(engine):
    from sqlalchemy.orm import Session

    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        service = session.get(Service, "checkout-service")
        service.seed = 999
        session.add(Fault(service_name=service.name, scenario_id="bad-config", active=True))
        session.flush()
        raise RuntimeError("intentional rollback")
    with Session(engine) as session:
        assert session.get(Service, "checkout-service").seed == 42
        assert session.scalar(select(func.count()).select_from(Fault)) == 0
        assert session.scalar(select(func.count()).select_from(MetricSummary)) == 0
        assert session.scalar(select(func.count()).select_from(SimulationLog)) == 0


def test_migration_matches_models(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_wall_clock_latency_is_observable(client, auth, activate, monkeypatch):
    activate("checkout-service", "slow-checkout")
    monkeypatch.setattr("opspilot.api.replay_window", lambda ms: time.sleep(ms / 1000))
    start = time.perf_counter()
    response = client.post("/api/v1/simulator/checkout-service/request", headers=auth)
    assert response.status_code == 200
    assert time.perf_counter() - start >= 0.55
    assert response.json()["results"][0]["latency_ms"] >= 550


def test_openapi_has_concrete_schemas_and_security(client):
    schema = client.get("/openapi.json").json()
    fault_api = schema["paths"]["/api/v1/faults"]["post"]
    assert fault_api["security"] == [{"HTTPBearer": []}]
    assert "FaultCreate" in schema["components"]["schemas"]
    assert "MetricOut" in schema["components"]["schemas"]


@pytest.mark.parametrize(
    ("service", "scenario"),
    [
        ("checkout-service", "slow-checkout"),
        ("payment-service", "payment-unavailable"),
        ("inventory-service", "inventory-db-exhaustion"),
        ("payment-service", "worker-saturation"),
        ("checkout-service", "bad-config"),
    ],
)
def test_fault_scenario_replay(client, auth, activate, workload, service, scenario):
    runs = []
    for _ in range(2):
        response = client.post(
            "/api/v1/fixtures/reset",
            headers=auth,
            json={
                "services": SERVICES,
                "seed": 314159,
            },
        )
        assert response.status_code == 200
        activate(service, scenario)
        runs.append(workload(service, count=30, interval=0))
    assert runs[0]["results"] == runs[1]["results"]
    for key in (
        "requests",
        "errors",
        "error_rate",
        "avg_latency_ms",
        "p95_latency_ms",
        "worker_utilization",
        "db_pool_utilization",
        "status_counts",
    ):
        assert metric_for(runs[0], service)[key] == metric_for(runs[1], service)[key]
