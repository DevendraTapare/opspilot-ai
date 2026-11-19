"""Real local browser-test stack in a fresh schema of the dedicated test database.

Only synthetic human credentials are used. No main simulator fixtures are touched.
"""

import asyncio
import getpass
import hashlib
import json
import os
import secrets
import socket
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

import uvicorn
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluations.runners.environment import Environment
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.config import Settings
from opspilot.dashboard.api import create_dashboard
from opspilot.dashboard.config import DashboardSettings
from opspilot.durable.cli import RunnerSettings
from opspilot.durable.operator import OperatorSettings
from opspilot.durable.persistence import run_async
from opspilot.gateway.authorizer import create_authorizer
from opspilot.gateway.contracts import READ_TOOLS, TOOLS
from opspilot.gateway.mcp_server import create_mcp_app
from opspilot.gateway.security import AuthorizerSettings, GatewaySettings
from opspilot.main import create_app
from opspilot.models import ActionExecution

ROOT = Path(__file__).resolve().parents[1]
TEST_HUMAN = os.environ.get(
    "OPSPILOT_BROWSER_TEST_HUMAN", "stage6-synthetic-browser-human-" + "h" * 40
)
TEST_KEY = os.environ.get("OPSPILOT_BROWSER_TEST_KEY", "stage6-bff-test-key-" + "k" * 40)


class Host:
    def __init__(self, app, port=0):
        self.app, self.port = app, port

    def start(self):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", self.port))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app, log_config=None, access_log=False, ws="none", timeout_graceful_shutdown=3
            )
        )
        self.thread = threading.Thread(
            target=lambda: run_async(self.server.serve(sockets=[self.socket])), daemon=True
        )
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("test server failed to start")
            time.sleep(0.02)
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(12)
        self.socket.close()
        if self.thread.is_alive():
            raise RuntimeError("test server did not stop")


@contextmanager
def serve(app, port=0):
    host = Host(app, port)
    try:
        yield host.start()
    finally:
        host.stop()


class DelayedFixture(FixtureDecisionModel):
    async def generate(self, stage, context, schema):
        await asyncio.sleep(0.3)
        return await super().generate(stage, context, schema)


def main():
    folder = Path(os.environ.get("OPSPILOT_BROWSER_TEST_ARTIFACT_DIR", ROOT / "artifacts"))
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT / "artifacts"):
        raise ValueError("browser test artifacts must stay inside this project")
    folder.mkdir(parents=True, exist_ok=True)
    ready = folder / "stage6-browser-stack.ready"
    stop = folder / "stage6-browser-stack.stop"
    values = dotenv_values(ROOT / ".env")
    from sqlalchemy.engine import URL

    url = URL.create(
        "postgresql+psycopg",
        username="opspilot_test",
        password=values.get("POSTGRES_PASSWORD", "unused-when-explicit-test-url-is-configured"),
        host="127.0.0.1",
        port=int(
            os.environ.get("OPSPILOT_TEST_DB_PORT", values.get("OPSPILOT_TEST_DB_PORT", "55433"))
        ),
        database="opspilot_stage1_test",
    ).render_as_string(hide_password=False)
    url = os.environ.get("OPSPILOT_BROWSER_TEST_DATABASE_URL", url)
    # Environment.start creates and migrates an isolated UUID schema; its read-only stack
    # remains independent. This harness starts a second, action-enabled sandbox stack.
    env = Environment(url)
    with env.start(), ExitStack() as stack:
        reader, executor, delegation, signing, control = [secrets.token_hex(32) for _ in range(5)]
        policies = json.dumps(
            [
                {
                    "subject": subject,
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "services": ["checkout-service", "payment-service", "inventory-service"],
                    "tools": list(tools),
                }
                for subject, token, tools in [
                    ("incident-reader", reader, READ_TOOLS),
                    ("durable-executor", executor, TOOLS),
                ]
            ]
        )
        registry = json.dumps(
            [
                {
                    "subject": "synthetic-browser-human",
                    "os_user": getpass.getuser(),
                    "token_sha256": hashlib.sha256(TEST_HUMAN.encode()).hexdigest(),
                    "services": ["checkout-service", "payment-service", "inventory-service"],
                    "actions": [
                        "restart_simulated_worker",
                        "rollback_simulated_configuration",
                        "reset_simulated_dependency",
                    ],
                }
            ]
        )
        backend = stack.enter_context(
            serve(
                create_authorizer(
                    AuthorizerSettings(
                        database_url=url,
                        callers=policies,
                        delegation_key=delegation,
                        approval_key=signing,
                        actions_enabled=True,
                        requests_per_minute=600,
                        _env_file=None,
                    ),
                    env.engine,
                )
            )
        )
        mcp = stack.enter_context(
            serve(
                create_mcp_app(
                    GatewaySettings(
                        callers=policies,
                        delegation_key=delegation,
                        backend_url=backend,
                        requests_per_minute=600,
                        timeout_seconds=10,
                    )
                )
            )
        )
        simulator = stack.enter_context(
            serve(
                create_app(
                    Settings(database_url=url, control_token=control, _env_file=None), env.engine
                )
            )
        )
        if os.environ.get("OPSPILOT_BROWSER_TEST_BASELINE") == "1":
            import httpx2

            for service in ["checkout-service", "payment-service", "inventory-service"]:
                response = httpx2.post(
                    simulator + f"/api/v1/simulator/{service}/workloads",
                    headers={"Authorization": "Bearer " + control},
                    json={"count": 12, "arrival_interval_ms": 25},
                    timeout=15,
                )
                response.raise_for_status()
        # Reuse the generated test data schema as checkpointer namespace, allowed by policy.
        runner = RunnerSettings(
            database_url=url,
            mcp_url=mcp + "/mcp",
            mcp_token=executor,
            checkpoint_schema=env.schema,
            _env_file=None,
        )
        operator = OperatorSettings(
            database_url=url, approval_key=signing, operators=registry, _env_file=None
        )
        settings = DashboardSettings(
            service_key=TEST_KEY,
            reader_token=reader,
            api_url=simulator,
            control_token=control,
            origin="http://127.0.0.1:3001",
            actions_enabled=True,
            _env_file=None,
        )
        # Establish a bounded pool before Chromium's process startup competes
        # with Windows Docker forwarding. This changes no action/tool deadline.
        with ExitStack() as warm:
            for _ in range(4):
                warm.enter_context(env.engine.connect())
        app = create_dashboard(
            settings,
            runner,
            operator,
            env.engine,
            env.engine,
            model_factory=lambda mode, budget: (
                DelayedFixture() if budget <= 0.2 else FixtureDecisionModel()
            ),
        )
        host = Host(app, 8087)
        host.start()
        stack.callback(host.stop)
        controller = FastAPI()

        @controller.post("/{operation}")
        def operation(operation: str, request: Request):
            if request.headers.get("x-test-key") != TEST_KEY:
                raise HTTPException(401)
            if operation == "outage":
                host.stop()
            elif operation == "recover":
                host.start()
            else:
                raise HTTPException(404)
            return {"status": operation}

        @controller.get("/effects")
        def effects(request: Request):
            if request.headers.get("x-test-key") != TEST_KEY:
                raise HTTPException(401)
            with Session(env.engine) as session:
                count = session.scalar(select(func.count()).select_from(ActionExecution))
            return {"effects": count}

        stack.enter_context(serve(controller, 8088))
        ready.write_text(env.schema)
        print(
            "Stage 6 isolated browser stack ready: API 8087, test-only lifecycle controller 8088.",
            flush=True,
        )
        try:
            while not stop.exists():
                time.sleep(0.25)
        finally:
            ready.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Browser test stack unavailable; no main fixtures were changed.", flush=True)
        raise SystemExit(2) from None
