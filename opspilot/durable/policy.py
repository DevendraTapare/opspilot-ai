"""Immutable action intent and current-state checks shared by issuer and executor."""

import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import select

from opspilot.gateway.approvals import ACTION_SCENARIOS, utc
from opspilot.gateway.contracts import ErrorCode, GatewayError
from opspilot.gateway.security import canonical
from opspilot.models import (
    DurableAudit,
    Fault,
    Incident,
    IncidentEvent,
    MetricSummary,
    RemediationApproval,
    Service,
)
from opspilot.observability import observed


@observed("audit.transition_append_attempt")
def audit(session, run_id, kind, detail=None, actor="durable-executor"):
    session.add(DurableAudit(run_id=run_id, actor=actor, kind=kind, detail=detail or {}))


def current_preconditions(session, incident_id, service, tool):
    incident = session.get(Incident, incident_id)
    fault = session.scalar(
        select(Fault).where(Fault.service_name == service, Fault.active.is_(True))
    )
    if (
        not incident
        or incident.status != "open"
        or not fault
        or tool not in ACTION_SCENARIOS
        or fault.scenario_id not in ACTION_SCENARIOS[tool]
    ):
        raise GatewayError(ErrorCode.STALE_APPROVAL)
    target = session.get(Service, service)
    event = session.scalar(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at.desc(), IncidentEvent.id.desc())
        .limit(1)
    )
    metrics = {}
    for name in sorted({incident.service_name, service}):
        metric = session.scalar(
            select(MetricSummary)
            .where(MetricSummary.service_name == name)
            .order_by(MetricSummary.created_at.desc(), MetricSummary.id.desc())
            .limit(1)
        )
        if not metric:
            raise GatewayError(ErrorCode.STALE_APPROVAL)
        metrics[name] = metric.id
    return {
        "fault_id": fault.id,
        "generation": target.generation,
        "incident_service": incident.service_name,
        "incident_status": incident.status,
        "incident_event_id": event.id if event else None,
        "metric_ids": metrics,
    }


def fingerprint(value):
    args = dict(value["arguments"])
    args.pop("action_fingerprint", None)
    payload = {
        name: value[name]
        for name in [
            "run_id",
            "incident_id",
            "tool",
            "service_name",
            "risk",
            "evidence",
            "preconditions",
            "verification_plan",
            "expires_at",
        ]
    }
    if not isinstance(payload["expires_at"], str):
        payload["expires_at"] = utc(payload["expires_at"]).isoformat()
    payload["arguments"] = args
    payload["binding_version"] = 1
    return hashlib.sha256(canonical(payload)).hexdigest()


def approval_dict(request):
    return {
        name: getattr(request, name)
        for name in [
            "run_id",
            "incident_id",
            "tool",
            "arguments",
            "service_name",
            "risk",
            "evidence",
            "preconditions",
            "verification_plan",
            "expires_at",
        ]
    }


def check_integrity(request):
    if not hmac.compare_digest(fingerprint(approval_dict(request)), request.fingerprint):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)


def effective_state(request):
    if request.state in {"pending", "approved"} and utc(request.expires_at) <= datetime.now(UTC):
        return "expired"
    return request.state


def check_live_approval(session, request, *, allow_consumed=False):
    check_integrity(request)
    state = effective_state(request)
    if state == "expired":
        raise GatewayError(ErrorCode.APPROVAL_EXPIRED)
    if state == "revoked":
        raise GatewayError(ErrorCode.APPROVAL_REVOKED)
    if state != "approved" and not (allow_consumed and state == "consumed"):
        raise GatewayError(
            ErrorCode.APPROVAL_USED if state == "consumed" else ErrorCode.APPROVAL_REQUIRED
        )
    if (
        state == "approved"
        and current_preconditions(session, request.incident_id, request.service_name, request.tool)
        != request.preconditions
    ):
        raise GatewayError(ErrorCode.STALE_APPROVAL)


def bound_request(session, caller, args):
    request = session.get(RemediationApproval, str(args.approval_id))
    if not request:
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    check_integrity(request)
    exact = args.model_dump(mode="json", exclude_none=True)
    if (
        request.run_id != str(args.run_id)
        or request.fingerprint != args.action_fingerprint
        or canonical(request.arguments) != canonical(exact)
        or caller.subject != "durable-executor"
    ):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    return request
