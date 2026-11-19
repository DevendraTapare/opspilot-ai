"""Fixed, parameterized queries with scope checks performed before access."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.gateway.approvals import utc
from opspilot.gateway.contracts import (
    DependencyData,
    DeploymentPage,
    ErrorCode,
    EventData,
    GatewayError,
    HealthData,
    IncidentData,
    IncidentPage,
    LogPage,
    MetricPage,
)
from opspilot.gateway.security import Caller, check_scope
from opspilot.models import (
    DeploymentEvent,
    Fault,
    Incident,
    IncidentEvent,
    MetricSummary,
    SimulationLog,
)
from opspilot.schemas import DeploymentOut, IncidentOut, LogOut, MetricOut
from opspilot.topology import DEPENDENCIES


def health(session: Session, name: str) -> HealthData:
    metric = session.scalar(
        select(MetricSummary)
        .where(MetricSummary.service_name == name)
        .order_by(MetricSummary.created_at.desc(), MetricSummary.id.desc())
        .limit(1)
    )
    fault = session.scalar(select(Fault).where(Fault.service_name == name, Fault.active.is_(True)))
    status = "unknown"
    if metric and (not fault or utc(metric.created_at) >= utc(fault.created_at)):
        status = (
            "degraded" if metric.error_rate >= 0.2 or metric.p95_latency_ms >= 300 else "healthy"
        )
    return HealthData(
        service_name=name,
        status=status,
        evidence="latest_metric_window" if metric else "no_observations",
        observed_at=utc(metric.created_at).isoformat() if metric else None,
        active_fault=fault.scenario_id if fault else None,
        metric=MetricOut.model_validate(metric) if metric else None,
    )


def page(session, statement, args, output_model, page_model):
    rows = list(session.scalars(statement.limit(args.limit + 1).offset(args.offset)))
    return page_model(
        items=[output_model.model_validate(row) for row in rows[: args.limit]],
        next_offset=args.offset + args.limit if len(rows) > args.limit else None,
    )


def read_observation(session: Session, caller: Caller, name: str, args):
    service = args.service_name
    check_scope(caller, name, service)
    if name == "list_incidents":
        statement = select(Incident).where(Incident.service_name == service)
        if args.status:
            statement = statement.where(Incident.status == args.status)
        return page(
            session,
            statement.order_by(Incident.opened_at.desc(), Incident.id.desc()),
            args,
            IncidentOut,
            IncidentPage,
        )
    if name == "get_incident":
        incident = session.scalar(
            select(Incident).where(
                Incident.id == str(args.incident_id), Incident.service_name == service
            )
        )
        if not incident:
            raise GatewayError(ErrorCode.NOT_FOUND)
        rows = list(
            session.scalars(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident.id)
                .order_by(IncidentEvent.created_at.desc(), IncidentEvent.id.desc())
                .limit(args.event_limit + 1)
            )
        )
        return IncidentData(
            incident=IncidentOut.model_validate(incident),
            events=[
                EventData(
                    id=row.id,
                    kind=row.kind,
                    created_at=utc(row.created_at).isoformat(),
                    metric_id=row.detail.get("metric_id"),
                    run_id=row.detail.get("run_id"),
                )
                for row in rows[: args.event_limit]
            ],
            events_truncated=len(rows) > args.event_limit,
        )
    if name == "get_service_health":
        return health(session, service)
    if name == "get_service_metrics":
        return page(
            session,
            select(MetricSummary)
            .where(MetricSummary.service_name == service)
            .order_by(MetricSummary.created_at.desc(), MetricSummary.id.desc()),
            args,
            MetricOut,
            MetricPage,
        )
    if name == "search_service_logs":
        statement = select(SimulationLog).where(SimulationLog.service_name == service)
        if args.query:
            statement = statement.where(SimulationLog.code.contains(args.query, autoescape=True))
        if args.level:
            statement = statement.where(SimulationLog.level == args.level)
        return page(
            session,
            statement.order_by(SimulationLog.created_at.desc(), SimulationLog.id.desc()),
            args,
            LogOut,
            LogPage,
        )
    if name == "list_recent_deployments":
        result = page(
            session,
            select(DeploymentEvent)
            .where(DeploymentEvent.service_name == service)
            .order_by(DeploymentEvent.created_at.desc(), DeploymentEvent.id.desc()),
            args,
            DeploymentOut,
            DeploymentPage,
        )
        for item in result.items:
            item.config = {
                key: value
                for key, value in item.config.items()
                if key in {"tax_mode", "seed", "generation", "action", "approval_id"}
                and isinstance(value, (str, int, bool))
            }
        return result
    if name == "get_dependency_status":
        dependencies = DEPENDENCIES[service]
        if not set(dependencies).issubset(caller.services):
            raise GatewayError(ErrorCode.FORBIDDEN)
        return DependencyData(
            service_name=service, dependencies=[health(session, d) for d in dependencies]
        )
    raise GatewayError(ErrorCode.UNKNOWN_TOOL)
