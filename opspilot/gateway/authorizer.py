"""Separate authorization/execution service. No grant-issuance endpoint exists."""

import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from opspilot.db import make_engine, session_factory
from opspilot.gateway.approvals import execute_approved_action
from opspilot.gateway.contracts import (
    ACTION_TOOLS,
    MAX_HTTP_BYTES,
    MAX_RESULT_BYTES,
    SUPERVISION_TOOLS,
    TOOLS,
    WRITE_TOOLS,
    DenialInput,
    ErrorCode,
    GatewayError,
    ToolResponse,
    failure,
    validate_arguments,
)
from opspilot.gateway.observations import read_observation
from opspilot.gateway.security import (
    AuthorizerSettings,
    RateLimiter,
    check_scope,
    verify_delegation,
)
from opspilot.logging import configure_logging
from opspilot.models import GatewayAudit


def sanitize(value):
    if isinstance(value, str):
        return "".join(char if char.isprintable() else " " for char in value)[:256]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


class BodyLimit:
    """Bound streamed bodies too, before FastAPI or the SDK parses JSON."""

    def __init__(self, app, maximum=MAX_HTTP_BYTES, timeout_seconds=5):
        self.app, self.maximum, self.timeout_seconds = app, maximum, timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                with anyio.fail_after(remaining):
                    message = await receive()
            except TimeoutError:
                logging.warning("gateway_http_body_rejected", extra={"event": "REQUEST_TIMEOUT"})
                return await JSONResponse({"error": "REQUEST_TIMEOUT"}, status_code=408)(
                    scope, receive, send
                )
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.maximum:
                logging.warning("gateway_http_body_rejected", extra={"event": "REQUEST_TOO_LARGE"})
                response = JSONResponse({"error": "REQUEST_TOO_LARGE"}, status_code=413)
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_authorizer(settings: AuthorizerSettings | None = None, engine=None) -> FastAPI:
    settings = settings or AuthorizerSettings()
    policies, limiter = settings.policies(), RateLimiter()
    owned = engine is None
    engine = engine or make_engine(settings.database_url.get_secret_value())
    sessions = session_factory(engine)

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        yield
        if owned:
            engine.dispose()

    app = FastAPI(
        title="OpsPilot sandbox authorization service",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BodyLimit)

    @app.get("/health/ready")
    def ready():
        try:
            with sessions() as session:
                version = session.scalar(text("SELECT version_num FROM alembic_version"))
                session.scalar(select(GatewayAudit.id).limit(1))
            if version != "0004_dashboard":
                raise ValueError("migration")
            return {"status": "ready", "actions_enabled": settings.actions_enabled}
        except (SQLAlchemyError, ValueError):
            return JSONResponse({"status": "unavailable"}, status_code=503)

    def handle(path, name, headers, raw):
        from opspilot.observability import attributes, remote_context, span

        with span(
            "execute_tool authorization-backend",
            operation="execute_tool",
            parent=remote_context(headers),
        ):
            attributes(**{"gen_ai.tool.name": name})
            return dispatch(path, name, headers, raw)

    def dispatch(path, name, headers, raw):
        request_id = str(uuid4())
        try:
            subject, request_id = verify_delegation(settings, headers, path, raw)
            caller = policies.get(subject)
            if caller is None:
                raise GatewayError(ErrorCode.FORBIDDEN)
        except GatewayError as exc:
            logging.warning("gateway_invalid_service_assertion")
            return failure(exc.code, request_id)
        try:
            with sessions.begin() as session:
                if engine.dialect.name == "postgresql":
                    session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                    session.execute(text("SET LOCAL lock_timeout = '1000ms'"))
                audit = GatewayAudit(
                    request_id=request_id,
                    subject=subject,
                    tool=name if name in TOOLS else "unknown_tool",
                    outcome="received",
                )
                session.add(audit)
                session.flush()  # Unique request ID rejects replayed service assertions.
                binding = {}
                try:
                    with session.begin_nested():
                        if not limiter.allow(subject + ":all", settings.requests_per_minute):
                            raise GatewayError(ErrorCode.RATE_LIMITED)
                        try:
                            arguments = json.loads(raw)
                        except ValueError:
                            raise GatewayError(ErrorCode.INVALID_ARGUMENTS) from None
                        args = validate_arguments(name, arguments)
                        binding["service_name"] = args.service_name
                        check_scope(caller, name, args.service_name)
                        if name in WRITE_TOOLS or name in SUPERVISION_TOOLS:
                            binding["approval_id"] = (
                                str(args.approval_id) if args.approval_id else None
                            )
                            binding["action_request_id"] = str(args.request_id)
                            if name in WRITE_TOOLS and not limiter.allow(
                                subject + ":action", settings.actions_per_minute
                            ):
                                raise GatewayError(ErrorCode.RATE_LIMITED)
                        if name in ACTION_TOOLS:
                            data = execute_approved_action(session, settings, caller, name, args)
                        elif name in SUPERVISION_TOOLS:
                            from opspilot.durable.gateway import (
                                execution_status,
                                verify_remediation,
                            )

                            if name == "verify_simulated_remediation":
                                data = verify_remediation(session, caller, args)
                            else:
                                data = execution_status(session, caller, args)
                        else:
                            data = read_observation(session, caller, name, args)
                        output = ToolResponse[TOOLS[name][1]](
                            ok=True, request_id=request_id, data=data
                        ).model_dump(mode="json")
                        output = sanitize(output)
                        # Revalidate the exact data emitted on the wire.
                        ToolResponse[TOOLS[name][1]].model_validate_json(json.dumps(output))
                        if len(json.dumps(output).encode()) > MAX_RESULT_BYTES:
                            raise GatewayError(ErrorCode.RESULT_TOO_LARGE)
                    audit.outcome = "success"
                except GatewayError as exc:
                    output = failure(exc.code, request_id)
                    audit.outcome = exc.code.value
                except (ValueError, TypeError):
                    output = failure(ErrorCode.DOWNSTREAM_UNAVAILABLE, request_id)
                    audit.outcome = ErrorCode.DOWNSTREAM_UNAVAILABLE.value
                for field, value in binding.items():
                    setattr(audit, field, value)
            return output
        except IntegrityError:
            return failure(ErrorCode.DUPLICATE_REQUEST, request_id)
        except SQLAlchemyError:
            logging.error("gateway_persistence_unavailable")
            return failure(ErrorCode.DOWNSTREAM_UNAVAILABLE, request_id)

    @app.post("/v1/tools/{name}")
    async def tool(name: str, request: Request):
        raw = await request.body()
        return await anyio.to_thread.run_sync(handle, request.url.path, name, request.headers, raw)

    def save_denial(path, headers, raw):
        try:
            subject, request_id = verify_delegation(settings, headers, path, raw)
            if subject not in policies:
                raise ValueError("unknown caller")
            value = DenialInput.model_validate_json(raw)
            with sessions.begin() as session:
                session.add(
                    GatewayAudit(
                        request_id=request_id,
                        subject=subject,
                        tool=value.tool,
                        service_name=value.service_name,
                        outcome=value.outcome,
                    )
                )
            return {"recorded": True}
        except IntegrityError:
            return {"recorded": True}
        except (GatewayError, ValueError, SQLAlchemyError):
            return JSONResponse({"recorded": False}, status_code=503)

    @app.post("/v1/denials")
    async def denial(request: Request):
        return await anyio.to_thread.run_sync(
            save_denial, request.url.path, request.headers, await request.body()
        )

    return app
