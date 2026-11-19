"""Loopback-only BFF backend. MCP clients and model outputs cannot issue approvals."""

from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import httpx2
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opspilot.dashboard import readmodels as views
from opspilot.dashboard.jobs import Jobs, real_model_available
from opspilot.dashboard.security import Security
from opspilot.durable.contracts import ExecutionError
from opspilot.durable.operator import authenticate_operator, decide_authorized
from opspilot.gateway.authorizer import BodyLimit
from opspilot.gateway.contracts import ACTION_TOOLS, READ_TOOLS, SUPERVISION_TOOLS, GatewayError
from opspilot.gateway.observations import DEPENDENCIES
from opspilot.models import DashboardRun, Incident
from opspilot.schemas import FaultCreate


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    credential: SecretStr = Field(min_length=32, max_length=256)


class Launch(Input):
    request_id: UUID
    incident_id: UUID
    mode: Literal["real", "fixture"]
    max_seconds: float = Field(default=180, ge=0.1, le=180)


class Decision(Input):
    decision: Literal["approve", "reject"]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def create_dashboard(settings, runner, operator, engine, operator_engine, model_factory=None):
    security = Security(settings, operator, operator_engine)
    jobs = Jobs(engine, runner, settings, model_factory)

    @asynccontextmanager
    async def lifespan(app):
        jobs.recover()
        yield
        await jobs.close()

    app = FastAPI(
        title="OpsPilot local dashboard API",
        version="0.6.0",
        lifespan=lifespan,
        dependencies=[Depends(security.boundary)],
    )
    app.state.jobs = jobs
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def limits(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "INVALID_ARGUMENTS"}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({"detail": "DATABASE_UNAVAILABLE"}, status_code=503)

    @app.exception_handler(ExecutionError)
    async def policy_error(request, exc):
        return JSONResponse({"detail": exc.code}, status_code=409)

    @app.exception_handler(GatewayError)
    async def gateway_policy_error(request, exc):
        return JSONResponse({"detail": exc.code.value}, status_code=409)

    def human(request):
        principal = security.principal(request)
        security.limit("write:" + principal.subject)
        return principal

    def scoped(principal, service):
        if service not in principal.services:
            raise HTTPException(403, "RESOURCE_FORBIDDEN")

    @app.get("/health/ready")
    def ready():
        with engine.connect() as conn:
            revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0004_dashboard":
            raise HTTPException(503, "MIGRATION_REQUIRED")
        return {"status": "ready", "migration": revision}

    @app.get("/meta")
    def meta(request: Request):
        principal = security.principal(request, False)
        return {
            "real_model_available": real_model_available(),
            "actions_enabled": settings.actions_enabled,
            "session": {"subject": principal.subject, "services": sorted(principal.services)}
            if principal
            else None,
        }

    @app.post("/session")
    def login(body: Login, response: Response):
        security.limit("login", 5)
        try:
            principal = authenticate_operator(
                operator.operators.get_secret_value(), body.credential.get_secret_value()
            )
        except (ExecutionError, ValueError):
            raise HTTPException(401, "OPERATOR_AUTHENTICATION_FAILED") from None
        security.issue(principal, response)
        return {"subject": principal.subject}

    @app.delete("/session")
    def logout(request: Request, response: Response):
        security.revoke(request, response)
        return {"status": "signed_out"}

    @app.get("/overview")
    def overview():
        return {
            "services": views.services(engine),
            "incidents": views.incidents(engine),
            "runs": views.runs(engine),
            "approvals": views.approvals(engine),
        }

    @app.get("/incidents")
    def incidents():
        return views.incidents(engine)

    @app.get("/incidents/{identity}")
    def incident(identity: UUID):
        value = views.incident_detail(engine, str(identity))
        if not value:
            raise HTTPException(404, "INCIDENT_NOT_FOUND")
        return value

    @app.get("/runs")
    def runs():
        return views.runs(engine)

    @app.get("/runs/{identity}")
    def run(identity: UUID):
        value = views.run_detail(engine, str(identity))
        if not value:
            raise HTTPException(404, "RUN_NOT_FOUND")
        return value

    @app.post("/runs", status_code=202)
    async def launch(body: Launch, request: Request):
        principal = human(request)
        if body.mode == "real" and not real_model_available():
            raise HTTPException(503, "REAL_MODEL_NOT_CONFIGURED")
        identity = str(body.request_id)
        with Session(engine) as session, session.begin():
            incident = session.get(Incident, str(body.incident_id))
            if not incident:
                raise HTTPException(404, "INCIDENT_NOT_FOUND")
            scoped(principal, incident.service_name)
            old = session.get(DashboardRun, identity)
            if old:
                if old.incident_id != str(body.incident_id) or old.mode != body.mode:
                    raise HTTPException(409, "REQUEST_ID_REUSED")
                return {"run_id": identity, "status": old.status}
            if len(jobs.tasks) >= 8:
                raise HTTPException(429, "QUEUE_FULL")
            if incident.status != "open":
                raise HTTPException(409, "INCIDENT_NOT_OPEN")
            session.add(
                DashboardRun(
                    id=identity,
                    incident_id=incident.id,
                    service_name=incident.service_name,
                    mode=body.mode,
                )
            )
        jobs.enqueue(identity, body.max_seconds)
        return {"run_id": identity, "status": "queued"}

    @app.post("/runs/{identity}/resume", status_code=202)
    async def resume(identity: UUID, request: Request):
        principal = human(request)
        from opspilot.durable.repository import Repository

        approval = Repository(engine).request(str(identity))
        scoped(principal, approval.service_name)
        if approval.tool not in principal.actions:
            raise HTTPException(403, "ACTION_FORBIDDEN")
        from opspilot.durable.policy import effective_state

        if not settings.actions_enabled:
            raise HTTPException(403, "SANDBOX_ACTIONS_DISABLED")
        if effective_state(approval) not in {"approved", "consumed"}:
            raise HTTPException(409, "HUMAN_APPROVAL_REQUIRED")
        try:
            jobs.enqueue(str(identity), resume=True)
        except ValueError:
            raise HTTPException(429, "QUEUE_FULL") from None
        return {"run_id": str(identity), "status": "resume_requested"}

    @app.get("/approvals")
    def approvals():
        return views.approvals(engine)

    @app.post("/approvals/{identity}/decision")
    def decision(identity: UUID, body: Decision, request: Request):
        principal = human(request)
        decide_authorized(
            operator_engine,
            operator,
            principal,
            str(identity),
            "approve" if body.decision == "approve" else "revoke",
            body.fingerprint,
        )
        return {
            "approval_id": str(identity),
            "state": "approved" if body.decision == "approve" else "revoked",
        }

    @app.post("/simulation", status_code=201)
    async def simulation(body: FaultCreate, request: Request):
        principal = human(request)
        scoped(principal, body.service_name)
        security.limit("simulation:" + principal.subject, 6)
        # Only the explicitly selected target is reset; other service fixtures stay intact.
        try:
            async with httpx2.AsyncClient(timeout=10) as client:
                headers = {"Authorization": "Bearer " + settings.control_token.get_secret_value()}
                calls = [
                    ("/api/v1/fixtures/reset", {"services": [body.service_name], "seed": 42}),
                    (
                        f"/api/v1/simulator/{body.service_name}/workloads",
                        {"count": 12, "arrival_interval_ms": 25},
                    ),
                    ("/api/v1/faults", body.model_dump(mode="json")),
                    (
                        f"/api/v1/simulator/{body.service_name}/workloads",
                        {"count": 30, "arrival_interval_ms": 0},
                    ),
                ]
                for path, payload in calls:
                    result = await client.post(
                        settings.api_url + path, headers=headers, json=payload
                    )
                    result.raise_for_status()
            with Session(engine) as session:
                row = session.scalar(
                    select(Incident).where(
                        Incident.service_name == body.service_name, Incident.status == "open"
                    )
                )
                if not row:
                    raise HTTPException(409, "NO_INCIDENT_OBSERVED")
                return {"incident_id": row.id, "service_name": row.service_name}
        except httpx2.HTTPError:
            raise HTTPException(503, "SIMULATOR_UNAVAILABLE_OR_PARTIAL") from None

    @app.get("/evaluations")
    def evaluations():
        try:
            return views.evaluations()
        except (OSError, ValueError):
            raise HTTPException(503, "RECORDED_REPORT_UNAVAILABLE") from None

    @app.get("/architecture")
    def architecture():
        return {
            "dependencies": DEPENDENCIES,
            "tools": [
                {"name": name, "access": access}
                for registry, access in (
                    (READ_TOOLS, "read-only"),
                    (ACTION_TOOLS, "human-approved action"),
                    (SUPERVISION_TOOLS, "durable supervision"),
                )
                for name in registry
            ],
            "persistence": "PostgreSQL + LangGraph PostgreSQL checkpointer",
        }

    return app
