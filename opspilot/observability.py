"""Content-free manual OTel instrumentation; explicit local export, never ambient OTLP."""

import inspect
import json
import os
import re
import threading
from contextlib import contextmanager, suppress
from functools import wraps
from pathlib import Path
from uuid import UUID

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SCHEMA_URL = "https://opentelemetry.io/schemas/1.37.0"
ROOT = Path(__file__).resolve().parents[1]
_provider = None
_lock = threading.Lock()
_configuration_lock = threading.Lock()


class LocalJSONExporter(SpanExporter):
    def __init__(self, path):
        path = Path(path).resolve()
        if not any(path.is_relative_to(ROOT / p) for p in ["artifacts", "evaluations/reports"]):
            raise ValueError("trace export must stay in project artifacts or evaluation reports")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path.with_name(f"{path.stem}.{os.getpid()}{path.suffix}")

    def export(self, spans):
        try:
            rows = []
            for s in spans:
                rows.append(
                    json.dumps(
                        {
                            "name": s.name,
                            "trace_id": f"{s.context.trace_id:032x}",
                            "span_id": f"{s.context.span_id:016x}",
                            "parent_span_id": f"{s.parent.span_id:016x}" if s.parent else None,
                            "start_ns": s.start_time,
                            "end_ns": s.end_time,
                            "status": s.status.status_code.name,
                            "attributes": dict(s.attributes or {}),
                            "events": [
                                {"name": e.name, "attributes": dict(e.attributes or {})}
                                for e in s.events
                            ],
                            "schema_url": SCHEMA_URL,
                        },
                        allow_nan=False,
                    )
                )
            with _lock, self.path.open("a", encoding="utf-8") as output:
                output.write("\n".join(rows) + "\n")
            return SpanExportResult.SUCCESS
        except OSError:
            # Observability availability must not authorize or interrupt an action transaction.
            return SpanExportResult.FAILURE


def configure_tracing(path=None, *, exporter=None):
    global _provider
    if _provider:
        _provider.shutdown()
    _provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "opspilot",
                "service.version": "stage5",
            }
        )
    )
    _provider.add_span_processor(SimpleSpanProcessor(exporter or LocalJSONExporter(path)))
    return _provider


def configure_from_environment():
    with _configuration_lock:
        if _provider is None and os.environ.get("OPSPILOT_TRACE_FILE"):
            configure_tracing(os.environ["OPSPILOT_TRACE_FILE"])


def attributes(**values):
    """Only enums, bounded counts and UUIDs; no prompts, URLs, args, logs or messages."""
    enums = {
        "gen_ai.operation.name": {"chat", "invoke_agent", "execute_tool"},
        "gen_ai.provider.name": {"openai-compatible", "ollama", "groq"},
        "gen_ai.agent.name": {"opspilot-investigator", "opspilot-durable"},
        "opspilot.mode": {"real", "fixture", "baseline"},
        "opspilot.service": {"checkout-service", "payment-service", "inventory-service"},
        "opspilot.node": {
            "triage",
            "investigation_planning",
            "readonly_mcp_execution",
            "evidence_assessment",
            "additional_investigation",
            "root_cause_proposal",
            "remediation_planning",
            "final_recommendation",
        },
        "opspilot.status": {
            "running",
            "completed",
            "abstained",
            "failed",
            "verified",
            "inconclusive",
            "budget_exhausted",
            "pending",
            "approved",
            "revoked",
            "executing",
            "blocked",
            "consumed",
            "awaiting_approval",
        },
    }
    from opspilot.gateway.contracts import TOOLS

    enums["gen_ai.tool.name"] = set(TOOLS)
    numeric = {
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "opspilot.tool_calls",
        "opspilot.requests",
        "opspilot.errors",
    }
    current = trace.get_current_span()
    for key, value in values.items():
        if (
            key in enums
            and isinstance(value, str)
            and value in enums[key]
            or key in numeric
            and type(value) is int
            and 0 <= value <= 10**12
        ):
            current.set_attribute(key, value)
        elif key in {"opspilot.run_id", "opspilot.incident_id", "opspilot.request_id"}:
            with suppress(ValueError):
                current.set_attribute(key, str(UUID(str(value))))


@contextmanager
def span(name, *, operation=None, kind=SpanKind.INTERNAL, parent=None):
    configure_from_environment()
    tracer = (_provider or trace.NoOpTracerProvider()).get_tracer(
        "opspilot.manual", "1.0.0", schema_url=SCHEMA_URL
    )
    with tracer.start_as_current_span(
        name, kind=kind, context=parent, record_exception=False, set_status_on_exception=False
    ) as current:
        if operation:
            attributes(**{"gen_ai.operation.name": operation})
        try:
            yield current
        except BaseException as exc:
            allowed = {
                "TimeoutError",
                "ValueError",
                "ModelFailure",
                "GatewayError",
                "ExecutionError",
                "BudgetExceeded",
                "CancelledError",
            }
            error = type(exc).__name__
            error = error if error in allowed else "Exception"
            current.set_attribute("error.type", error)
            current.add_event("exception", {"exception.type": error})
            current.set_status(Status(StatusCode.ERROR))
            raise


def carrier():
    output = {}
    TraceContextTextMapPropagator().inject(output)
    return {"traceparent": output["traceparent"]} if "traceparent" in output else {}


def remote_context(value):
    # Trace identity is correlation only, never authentication, approval or baggage.
    header = (value or {}).get("traceparent", "")
    if isinstance(header, str) and re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", header
    ):
        return TraceContextTextMapPropagator().extract({"traceparent": header})
    return None


def observed(name, *, operation=None, kind=SpanKind.INTERNAL):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with span(name, operation=operation, kind=kind):
                    return await function(*args, **kwargs)

            return asynchronous

        @wraps(function)
        def synchronous(*args, **kwargs):
            with span(name, operation=operation, kind=kind):
                return function(*args, **kwargs)

        return synchronous

    return decorate
