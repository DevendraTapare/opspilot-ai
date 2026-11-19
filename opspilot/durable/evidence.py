"""Verify cited facts against persisted telemetry, not merely a successful call ID."""

from opspilot.agent.evidence import bind_response, health, project
from opspilot.durable.contracts import ExecutionError
from opspilot.gateway.approvals import utc
from opspilot.gateway.security import canonical
from opspilot.models import DeploymentEvent, Incident, MetricSummary, SimulationLog
from opspilot.schemas import DeploymentOut, IncidentOut, LogOut, MetricOut


def check_evidence_content(session, observation):
    def row_value(model, schema, identity):
        row = session.get(model, identity)
        if row is None:
            raise ValueError("unknown evidence row")
        return schema.model_validate(row).model_dump(mode="json")

    def health_value(value):
        metric = value.get("metric")
        raw = row_value(MetricSummary, MetricOut, metric["id"]) if metric else None
        return health(
            {
                "service_name": value["service_name"],
                "metric": raw,
                "observed_at": utc(session.get(MetricSummary, metric["id"]).created_at).isoformat()
                if metric
                else None,
            }
        )

    try:
        name, data = observation.tool_name, observation.data
        args = {"service_name": observation.service_name}
        if name == "get_incident":
            args["incident_id"] = data["incident"]["id"]
            expected = project(
                name, {"incident": row_value(Incident, IncidentOut, data["incident"]["id"])}
            )
        elif name == "get_service_health":
            expected = health_value(data)
        elif name == "get_dependency_status":
            expected = {
                "service_name": data["service_name"],
                "dependencies": [health_value(d) for d in data["dependencies"]],
            }
        else:
            model, schema = {
                "list_incidents": (Incident, IncidentOut),
                "get_service_metrics": (MetricSummary, MetricOut),
                "search_service_logs": (SimulationLog, LogOut),
                "list_recent_deployments": (DeploymentEvent, DeploymentOut),
            }[name]
            expected = project(
                name,
                {
                    "items": [row_value(model, schema, v["id"]) for v in data["items"]],
                    "next_offset": data.get("next_offset"),
                },
            )
        bind_response(name, expected, args)
        if canonical(data) != canonical(expected):
            raise ValueError("altered evidence")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ExecutionError("EVIDENCE_CONTENT_MISMATCH") from None
