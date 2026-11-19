from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

pytestmark = pytest.mark.postgres


def test_concurrent_fault_activation_is_atomic(engine, client, auth):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock semantics only")

    def activate():
        return client.post(
            "/api/v1/faults",
            headers=auth,
            json={
                "service_name": "payment-service",
                "scenario_id": "payment-unavailable",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: activate(), range(2)))
    assert sorted(statuses) == [201, 409]
    assert len(client.get("/api/v1/faults?active=true").json()) == 1


def test_migration_round_trip(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration round trip")
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert "services" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "services" in inspect(connection).get_table_names()
