import io
import json
import logging
import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from opspilot.config import Settings
from opspilot.db import make_engine
from opspilot.logging import JsonFormatter
from opspilot.main import create_app
from opspilot.simulator.engine import FaultState, Fixture, Simulator


def test_determinism_and_seed_changes():
    def execute(seed):
        fixtures = {
            name: Fixture(seed, 0, 0)
            for name in ("checkout-service", "payment-service", "inventory-service")
        }
        simulator = Simulator(fixtures)
        return simulator.run("checkout-service", 12, 25)

    assert execute(42) == execute(42)
    assert execute(42) != execute(43)


def test_fault_resource_bounds_and_error_causality():
    fixtures = {
        name: Fixture(42, 0, 0)
        for name in ("checkout-service", "payment-service", "inventory-service")
    }
    fault = FaultState("inventory-fault", "inventory-db-exhaustion")
    fixtures["inventory-service"].fault = fault
    simulator = Simulator(fixtures)
    result = simulator.run("checkout-service", 1, 0)[0]
    assert result.status_code == 502
    assert result.fault == fault
    assert simulator.samples["payment-service"][0].status_code == 200
    assert simulator.samples["inventory-service"][0].status_code == 503
    assert len(simulator.resources["inventory-service"].connections) == 4


@pytest.mark.parametrize(
    "token", ["", "short", "replace-with-a-random-token-of-at-least-32-characters"]
)
def test_configuration_rejects_insecure_tokens(token):
    with pytest.raises(ValidationError):
        Settings(control_token=token, _env_file=None)


def test_health_distinguishes_unmigrated_database(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    app = create_app(Settings(control_token=secrets.token_hex(32), _env_file=None), engine=engine)
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 503
            response = client.get("/api/v1/services")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database operation unavailable"}
    finally:
        engine.dispose()


def test_http_logging_never_records_supplied_secrets(client, auth):
    secret = secrets.token_hex(32)
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("opspilot.http")
    logger.addHandler(handler)
    try:
        client.get(
            f"/unknown-{secret}?token={secret}", headers={"Authorization": f"Bearer {secret}"}
        )
        response = client.post(
            "/api/v1/fixtures/reset",
            headers=auth,
            json={
                "services": [secret],
                "password": secret,
            },
        )
        assert response.status_code == 422
        assert secret not in response.text
    finally:
        logger.removeHandler(handler)
    rows = [json.loads(line) for line in buffer.getvalue().splitlines()]
    assert len(rows) == 2
    assert secret not in buffer.getvalue()
    assert all("request_id" in row for row in rows)
    assert rows[0]["route"] == "unmatched"
    assert rows[1]["route"] == "/api/v1/fixtures/reset"


def test_exception_formatter_does_not_leak_exception_details():
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "secret-password",
        (),
        (ValueError, ValueError("secret-password"), None),
    )
    assert "secret-password" not in JsonFormatter().format(record)
