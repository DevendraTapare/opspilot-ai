"""Privileged fixture controller, restricted to a fresh schema in the test database."""

import hashlib
import json
import secrets
import socket
import threading
import time
from contextlib import ExitStack, contextmanager
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from evaluations.runners.contracts import PublicCase
from opspilot.db import make_engine
from opspilot.faults import activate, reset
from opspilot.gateway.authorizer import create_authorizer
from opspilot.gateway.contracts import READ_TOOLS
from opspilot.gateway.mcp_server import create_mcp_app
from opspilot.gateway.security import AuthorizerSettings, GatewaySettings
from opspilot.models import Base, Incident, MetricSummary, SimulationLog
from opspilot.schemas import FaultCreate, ResetRequest, ServiceName, WorkloadRequest
from opspilot.telemetry import execute_workload


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app, log_config=None, access_log=False, ws="none", timeout_graceful_shutdown=3
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("evaluation server unavailable")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("evaluation server did not stop")


class Outages:
    """Real HTTP 503 injection at the evaluation backend boundary, not a fake tool."""

    def __init__(self, app, controller):
        self.app, self.controller = app, controller

    async def __call__(self, scope, receive, send):
        tool = scope.get("path", "").removeprefix("/v1/tools/")
        if scope["type"] == "http" and tool in self.controller.fail_tools:
            return await JSONResponse({"status": "unavailable"}, status_code=503)(
                scope, receive, send
            )
        return await self.app(scope, receive, send)


class Environment:
    def __init__(self, raw_url):
        url = make_url(raw_url)
        if (
            url.database != "opspilot_stage1_test"
            or url.host not in {"localhost", "127.0.0.1", "test-db"}
            or url.drivername != "postgresql+psycopg"
        ):
            raise ValueError("evaluation requires the dedicated local PostgreSQL test database")
        self.admin = make_engine(raw_url)
        self.schema = "opspilot_test_" + uuid4().hex
        self.engine = None
        self.fail_tools = []

    @contextmanager
    def start(self):
        with ExitStack() as stack:
            try:
                with self.admin.begin() as c:
                    c.execute(text(f'CREATE SCHEMA "{self.schema}"'))
                self.engine = create_engine(
                    self.admin.url,
                    hide_parameters=True,
                    pool_pre_ping=True,
                    connect_args={"options": f"-csearch_path={self.schema}", "connect_timeout": 5},
                )
                with self.engine.begin() as c:
                    cfg = Config("alembic.ini")
                    cfg.attributes["connection"] = c
                    command.upgrade(cfg, "head")
                self.token = secrets.token_hex(32)
                policies = json.dumps(
                    [
                        {
                            "subject": "evaluation-reader",
                            "token_sha256": hashlib.sha256(self.token.encode()).hexdigest(),
                            "services": list(ServiceName),
                            "tools": list(READ_TOOLS),
                        }
                    ]
                )
                key = secrets.token_hex(32)
                settings = AuthorizerSettings(
                    database_url=self.engine.url.render_as_string(hide_password=False),
                    callers=policies,
                    delegation_key=key,
                    approval_key=secrets.token_hex(32),
                    actions_enabled=False,
                    requests_per_minute=600,
                    _env_file=None,
                )
                backend = stack.enter_context(
                    serve(Outages(create_authorizer(settings, self.engine), self))
                )
                gateway = GatewaySettings(
                    callers=policies,
                    delegation_key=key,
                    backend_url=backend,
                    timeout_seconds=10,
                    requests_per_minute=600,
                    _env_file=None,
                )
                self.url = stack.enter_context(serve(create_mcp_app(gateway))) + "/mcp"
                yield self
            finally:
                stack.close()
                if self.engine:
                    self.engine.dispose()
                with self.admin.begin() as c:
                    c.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
                self.admin.dispose()

    def prepare(self, case):
        # Names come only from internal metadata, in this controller's newly allocated schema.
        # No public/main database tables or unrelated fixtures can be reset.
        with self.engine.begin() as c:
            names = ", ".join(
                f'"{self.schema}"."{t.name}"'
                for t in Base.metadata.sorted_tables
                if t.name != "services"
            )
            c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        self.fail_tools = []
        with Session(self.engine) as s, s.begin():
            reset(s, ResetRequest(services=list(ServiceName), seed=case.seed))
            if case.history:
                activate(s, FaultCreate(service_name="checkout-service", scenario_id="bad-config"))
                execute_workload(
                    s, "checkout-service", WorkloadRequest(count=12, arrival_interval_ms=25)
                )
                reset(s, ResetRequest(services=list(ServiceName), seed=case.seed))
            execute_workload(
                s, "checkout-service", WorkloadRequest(count=12, arrival_interval_ms=25)
            )
            for fault in case.faults:
                activate(s, fault)
            # Independently sample each downstream service, including fail-fast hidden paths.
            for service in ["payment-service", "inventory-service"]:
                execute_workload(
                    s,
                    service,
                    WorkloadRequest(count=case.count, arrival_interval_ms=case.interval_ms),
                )
            execute_workload(
                s,
                case.target,
                WorkloadRequest(count=case.count, arrival_interval_ms=case.interval_ms),
            )
            incident = s.scalar(
                select(Incident).where(
                    Incident.service_name == case.target, Incident.status == "open"
                )
            )
            if not incident:
                # A suspected alert with real healthy observations: no invented fault/metric.
                incident = Incident(
                    service_name=case.target, title="Suspected service incident", status="open"
                )
                s.add(incident)
                s.flush()
            incident_id = incident.id
            if case.missing in {"metrics", "all"}:
                s.execute(delete(MetricSummary))
            if case.missing in {"logs", "all"}:
                s.execute(delete(SimulationLog))
            if case.contradict_logs:
                for log in s.scalars(select(SimulationLog)):
                    log.status_code = 200
                    log.latency_ms = 10
                    log.level = "INFO"
        self.fail_tools = case.fail_tools
        return PublicCase(incident_id=incident_id, service_name=case.target)
