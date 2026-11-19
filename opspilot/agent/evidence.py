"""Positive projection of operational observations; fixture truth never enters model context."""

from opspilot.agent.schemas import DiagnosticStep
from opspilot.gateway.contracts import READ_TOOLS, ToolResponse, validate_arguments
from opspilot.topology import DEPENDENCIES

METRIC_FIELDS = {
    "id",
    "run_id",
    "service_name",
    "incident_id",
    "requests",
    "errors",
    "error_rate",
    "avg_latency_ms",
    "p95_latency_ms",
    "max_latency_ms",
    "worker_utilization",
    "db_pool_utilization",
    "window_ms",
    "status_counts",
    "created_at",
}
INCIDENT_FIELDS = {"id", "service_name", "status", "opened_at", "resolved_at"}
LOG_FIELDS = {
    "id",
    "run_id",
    "service_name",
    "incident_id",
    "level",
    "status_code",
    "latency_ms",
    "created_at",
}


def pick(value, fields):
    return {k: v for k, v in value.items() if k in fields}


def health(value):
    # Health labels may depend directly on injected faults. Derive an observation-only label.
    metric = value.get("metric")
    return {
        "service_name": value["service_name"],
        "observed_at": value.get("observed_at"),
        "status": "unknown"
        if metric is None
        else (
            "degraded"
            if metric["error_rate"] >= 0.2 or metric["p95_latency_ms"] >= 300
            else "healthy"
        ),
        "metric": pick(metric, METRIC_FIELDS) if metric else None,
    }


def project(name: str, data: dict) -> dict:
    """No recursive denylist: only enumerated operational fields can pass."""
    if name == "get_incident":
        return {"incident": pick(data["incident"], INCIDENT_FIELDS)}
    if name == "get_service_health":
        return health(data)
    if name == "get_dependency_status":
        return {
            "service_name": data["service_name"],
            "dependencies": [health(d) for d in data["dependencies"]],
        }
    items = data.get("items", [])
    if name == "list_incidents":
        items = [pick(x, INCIDENT_FIELDS) for x in items]
    elif name == "get_service_metrics":
        items = [pick(x, METRIC_FIELDS) for x in items]
    elif name == "search_service_logs":
        # Canonical simulator codes name fixture causes, so do not expose them, even as logs.
        # Statuses, timings, levels and correlation IDs are real request observations.
        items = [pick(x, LOG_FIELDS) for x in items]
    elif name == "list_recent_deployments":
        items = [
            {
                **pick(x, {"id", "service_name", "created_at"}),
                "configuration": pick(x.get("config", {}), {"tax_mode"}),
            }
            for x in items
        ]
    else:
        raise ValueError("read tool not supported")
    return {"items": items, "next_offset": data.get("next_offset")}


def arguments_for(step: DiagnosticStep, incident_id: str, allowed_services: set[str]) -> dict:
    if step.tool_name not in READ_TOOLS or step.service_name not in allowed_services:
        raise ValueError("diagnostic scope rejected")
    fields = READ_TOOLS[step.tool_name][0].model_fields
    args = {"service_name": step.service_name.value}
    if "incident_id" in fields:
        if step.incident_id is not None and str(step.incident_id) != incident_id:
            raise ValueError("different incident rejected")
        args["incident_id"] = incident_id
    if "limit" in fields:
        args["limit"] = step.limit
    if "event_limit" in fields:
        args["event_limit"] = step.limit
    if "query" in fields:
        args["query"] = step.query
    return validate_arguments(step.tool_name, args).model_dump(mode="json")


def bind_response(name, data, arguments):
    """A structurally valid response must still belong to the requested resource."""
    service = arguments["service_name"]

    def bound_health(value, target):
        if value["service_name"] != target:
            raise ValueError("response service mismatch")
        if value.get("metric") and value["metric"]["service_name"] != target:
            raise ValueError("response metric service mismatch")

    if name == "get_incident":
        incident = data["incident"]
        if incident["service_name"] != service or str(incident["id"]) != str(
            arguments["incident_id"]
        ):
            raise ValueError("response incident mismatch")
    elif name == "get_service_health":
        bound_health(data, service)
    elif name == "get_dependency_status":
        if data["service_name"] != service:
            raise ValueError("response dependency root mismatch")
        targets = [d["service_name"] for d in data["dependencies"]]
        if len(targets) != len(set(targets)) or not set(targets) <= set(DEPENDENCIES[service]):
            raise ValueError("response topology mismatch")
        for value in data["dependencies"]:
            bound_health(value, value["service_name"])
    elif any(row["service_name"] != service for row in data.get("items", [])):
        raise ValueError("response page service mismatch")


def parse_response(name, result, arguments=None):
    if name not in READ_TOOLS:
        raise ValueError("read tool not supported")
    value = ToolResponse[READ_TOOLS[name][1]].model_validate(result)
    if not value.ok:
        return str(value.request_id), None, value.error.code.value
    data = value.data.model_dump(mode="json")
    if arguments is not None:
        bind_response(name, data, arguments)
    return str(value.request_id), project(name, data), None
