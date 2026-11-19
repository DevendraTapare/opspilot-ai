"""Incident detection and recovery from observed request summaries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.models import Incident, IncidentEvent, MetricSummary, now
from opspilot.observability import attributes, observed


@observed("incident.lifecycle")
def observe(session: Session, metric: MetricSummary) -> Incident | None:
    incident = session.scalar(
        select(Incident).where(
            Incident.service_name == metric.service_name, Incident.status == "open"
        )
    )
    attributes(
        **{
            "opspilot.service": metric.service_name,
            "opspilot.requests": metric.requests,
            "opspilot.errors": metric.errors,
        }
    )
    unhealthy = metric.error_rate >= 0.2 or metric.p95_latency_ms >= 300
    if unhealthy:
        if incident is None:
            incident = Incident(
                service_name=metric.service_name,
                title=f"Observed degradation in {metric.service_name}",
                scenario_id=metric.scenario_id,
                fault_id=metric.fault_id,
                status="open",
            )
            session.add(incident)
            session.flush()
            kind = "opened"
        else:
            kind = "observation"
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                kind=kind,
                detail={
                    "run_id": metric.run_id,
                    "metric_id": metric.id,
                    "error_rate": metric.error_rate,
                    "p95_latency_ms": metric.p95_latency_ms,
                    "scenario_id": metric.scenario_id,
                },
            )
        )
    elif incident:
        incident.status = "resolved"
        incident.resolved_at = now()
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                kind="recovered",
                detail={"run_id": metric.run_id, "metric_id": metric.id},
            )
        )
    if incident:
        attributes(
            **{
                "opspilot.incident_id": incident.id,
                "opspilot.status": "running" if unhealthy else "completed",
            }
        )
    return incident
