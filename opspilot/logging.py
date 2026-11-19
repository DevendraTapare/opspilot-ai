"""Allowlisted JSON records: never serialize headers, bodies, URLs, or exceptions."""

import json
import logging
from datetime import UTC, datetime

SAFE_FIELDS = ("request_id", "method", "route", "status_code", "duration_ms", "event")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": "request_failed" if record.exc_info else record.getMessage(),
        }
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            payload["trace_id"] = f"{context.trace_id:032x}"
            payload["span_id"] = f"{context.span_id:016x}"
        for key in SAFE_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    from opspilot.observability import configure_from_environment

    configure_from_environment()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn access logs can contain attacker-provided query strings.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
