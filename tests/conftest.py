"""SQLite portability tests plus identical API tests against isolated PostgreSQL schemas."""

import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.db import make_engine
from opspilot.main import create_app

TOKEN = "test-only-control-token-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(ROOT / "artifacts" / "pytest-local")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Connection tracebacks can expose driver kwargs; redact project credentials in reports."""
    from functools import lru_cache

    from dotenv import dotenv_values

    @lru_cache(maxsize=1)
    def secret_values():
        values = []
        sources = [dict(os.environ)] + [
            dotenv_values(ROOT / name) for name in [".env", ".runner.env", ".operator.env"]
        ]
        for source in sources:
            for key, value in source.items():
                if value and len(value) >= 16 and key.endswith(("TOKEN", "PASSWORD", "KEY", "URL")):
                    values.append(value)
                    if key.endswith("URL"):
                        try:
                            password = make_url(value).password
                            if password:
                                values.append(password)
                        except Exception:
                            pass
        return sorted(set(values), key=len, reverse=True)

    report = yield

    def clean(value):
        for secret in secret_values():
            value = value.replace(secret, "[REDACTED]")
        # Driver reprs can truncate a connection string inside the password,
        # so full-value substitution alone does not protect failed DB setup.
        value = re.sub(r"(?i)(password=)[^\s'\"]+", r"\1[REDACTED]", value)
        return value

    if report.failed and report.longrepr:
        report.longrepr = clean(str(report.longrepr))
    report.sections = [(key, clean(value)) for key, value in report.sections]
    return report


def migrate(engine):
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture(params=["sqlite", "postgres"])
def engine(request, tmp_path):
    if request.param == "sqlite":
        database = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
        migrate(database)
        yield database
        database.dispose()
        return

    raw_url = os.environ.get("OPSPILOT_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Dedicated PostgreSQL test database not configured")
    url = make_url(raw_url)
    if (
        url.database != "opspilot_stage1_test"
        or url.host not in {"test-db", "localhost", "127.0.0.1"}
        or url.drivername != "postgresql+psycopg"
    ):
        pytest.fail("Refusing tests outside the explicitly dedicated local test database")
    admin = make_engine(raw_url)
    schema = f"opspilot_test_{uuid4().hex}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    database = create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3},
        pool_pre_ping=True,
        hide_parameters=True,
    )
    try:
        migrate(database)
        yield database
    finally:
        database.dispose()
        # Only this test's fresh UUID schema is removed. No public schema or volumes are touched.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def app(engine):
    return create_app(Settings(control_token=TOKEN, _env_file=None), engine=engine)


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr("opspilot.api.replay_window", lambda milliseconds: None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def activate(client, auth):
    def execute(service, scenario):
        response = client.post(
            "/api/v1/faults",
            headers=auth,
            json={
                "service_name": service,
                "scenario_id": scenario,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return execute


@pytest.fixture
def workload(client, auth):
    def execute(service, count=12, interval=25):
        response = client.post(
            f"/api/v1/simulator/{service}/workloads",
            headers=auth,
            json={
                "count": count,
                "arrival_interval_ms": interval,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    return execute
