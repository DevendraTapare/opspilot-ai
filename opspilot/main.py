import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from opspilot.api import router
from opspilot.config import Settings, get_settings
from opspilot.db import make_engine, session_factory
from opspilot.logging import configure_logging


def create_app(settings: Settings | None = None, engine=None) -> FastAPI:
    settings = settings or get_settings()
    owned_engine = engine is None
    engine = engine or make_engine(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        yield
        if owned_engine:
            engine.dispose()

    app = FastAPI(
        title="OpsPilot AI — Stage 1",
        version="0.1.0",
        lifespan=lifespan,
        description="Local deterministic incident simulator. No production integrations or LLMs.",
    )
    app.state.settings = settings
    app.state.sessions = session_factory(engine)
    app.include_router(router)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = str(uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        logging.getLogger("opspilot.http").info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 3),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default includes rejected input; avoid echoing arbitrary secrets.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(error["loc"]), "type": error["type"], "msg": "Invalid value"}
                    for error in exc.errors()
                ]
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger("opspilot.db").error("database_operation_failed")
        return JSONResponse(status_code=503, content={"detail": "Database operation unavailable"})

    return app
