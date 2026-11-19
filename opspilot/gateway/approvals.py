"""Grant verification and bounded in-database simulator actions; no approval HTTP API."""

import getpass
import hashlib
import hmac
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.faults import deactivate, lock_services
from opspilot.gateway.contracts import ActionData, ActionInput, ErrorCode, GatewayError
from opspilot.gateway.security import AuthorizerSettings, Caller, canonical, check_scope
from opspilot.models import (
    ActionApproval,
    ActionExecution,
    DeploymentEvent,
    Fault,
    GatewayAudit,
    uid,
)
from opspilot.observability import observed

ACTION_SCENARIOS = {
    "restart_simulated_worker": {"worker-saturation"},
    "rollback_simulated_configuration": {"bad-config"},
    "reset_simulated_dependency": {"payment-unavailable", "inventory-db-exhaustion"},
}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def grant_signature(approval: ActionApproval, key: str) -> str:
    value = {
        field: getattr(approval, field)
        for field in (
            "id",
            "subject",
            "action",
            "service_name",
            "fault_id",
            "approved_by",
        )
    }
    value["expires_at"] = utc(approval.expires_at).isoformat()
    value["source"] = "interactive-local-operator"
    if approval.durable_request_id:
        value["durable_request_id"] = approval.durable_request_id
        value["durable_fingerprint"] = approval.durable_fingerprint
    return hmac.new(key.encode(), canonical(value), hashlib.sha256).hexdigest()


@observed("remediation.action_attempt")
def execute_approved_action(
    session: Session, settings: AuthorizerSettings, caller: Caller, action: str, args: ActionInput
) -> ActionData:
    if not settings.actions_enabled:
        raise GatewayError(ErrorCode.ACTIONS_DISABLED)
    check_scope(caller, action, args.service_name)
    if args.approval_id is None:
        raise GatewayError(ErrorCode.APPROVAL_REQUIRED)
    if caller.subject == "durable-executor" and (
        args.run_id is None or args.action_fingerprint is None
    ):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    names = {args.service_name}
    if args.run_id is not None:
        from opspilot.models import RemediationApproval

        pending = session.get(RemediationApproval, str(args.approval_id))
        if pending:
            names.add(pending.preconditions["incident_service"])
    lock_services(session, sorted(names))
    if session.get(ActionExecution, str(args.request_id)):
        raise GatewayError(ErrorCode.DUPLICATE_REQUEST)
    approval = session.scalar(
        select(ActionApproval).where(ActionApproval.id == str(args.approval_id)).with_for_update()
    )
    if not approval:
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    if (
        approval.subject != caller.subject
        or approval.action != action
        or approval.service_name != args.service_name
    ):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    expected = grant_signature(approval, settings.approval_key.get_secret_value())
    if not hmac.compare_digest(expected, approval.signature):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    durable_request = None
    if approval.durable_request_id:
        from opspilot.durable.policy import bound_request, check_live_approval

        durable_request = bound_request(session, caller, args)
        session.refresh(durable_request, with_for_update=True)
        if (
            durable_request.id != approval.durable_request_id
            or durable_request.fingerprint != approval.durable_fingerprint
            or durable_request.tool != action
        ):
            raise GatewayError(ErrorCode.APPROVAL_INVALID)
        check_live_approval(session, durable_request)
    elif (
        args.run_id is not None
        or args.action_fingerprint is not None
        or caller.subject == "durable-executor"
    ):
        raise GatewayError(ErrorCode.APPROVAL_INVALID)
    if utc(approval.expires_at) <= datetime.now(UTC):
        raise GatewayError(ErrorCode.APPROVAL_EXPIRED)
    if approval.consumed_by:
        raise GatewayError(ErrorCode.APPROVAL_USED)
    fault = session.scalar(
        select(Fault).where(Fault.service_name == args.service_name, Fault.active.is_(True))
    )
    if (
        not fault
        or fault.id != approval.fault_id
        or fault.scenario_id not in ACTION_SCENARIOS[action]
    ):
        raise GatewayError(ErrorCode.STALE_APPROVAL)
    deactivate(session, fault)
    approval.consumed_by = str(args.request_id)
    if durable_request:
        from opspilot.durable.policy import audit

        durable_request.state = "consumed"
        audit(
            session,
            durable_request.run_id,
            "action_committed",
            {"request_id": str(args.request_id), "fingerprint": durable_request.fingerprint},
        )
    session.add(
        ActionExecution(
            request_id=str(args.request_id),
            approval_id=approval.id,
            subject=caller.subject,
            action=action,
            service_name=args.service_name,
            fault_id=fault.id,
        )
    )
    session.add(
        DeploymentEvent(
            service_name=args.service_name,
            fault_id=fault.id,
            scenario_id=fault.scenario_id,
            kind="approved_simulated_action",
            config={"action": action, "approval_id": approval.id},
        )
    )
    return ActionData(
        action=action,
        service_name=args.service_name,
        fault_id=fault.id,
        approval_id=approval.id,
        execution_id=args.request_id,
    )


def approve_interactively(
    session: Session,
    settings: AuthorizerSettings,
    subject: str,
    action: str,
    service: str,
    fault_id: str,
    ttl: int,
) -> str:
    # This is an operator entry point, intentionally unreachable from MCP/HTTP.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Approval requires a real interactive operator terminal")
    caller = settings.policies().get(subject)
    if caller is None or action not in ACTION_SCENARIOS or not 30 <= ttl <= 600:
        raise ValueError("Invalid approval binding")
    check_scope(caller, action, service)
    fault = session.get(Fault, fault_id)
    if not fault or not fault.active or fault.service_name != service:
        raise ValueError("Approval requires the currently active fault on the selected service")
    if fault.scenario_id not in ACTION_SCENARIOS[action]:
        raise ValueError("Action does not remediate the selected fault scenario")
    phrase = f"APPROVE {action} {service}"
    print(
        f"Caller: {subject}\nAction: {action}\nService: {service}\nFault: {fault_id}\nTTL: {ttl}s"
    )
    if input(f"Type exactly '{phrase}' to authorize one execution: ") != phrase:
        raise RuntimeError("Operator did not approve")
    lock_services(session, [service])
    session.refresh(fault)
    if not fault.active or fault.scenario_id not in ACTION_SCENARIOS[action]:
        raise ValueError("Fault changed while the operator reviewed the action")
    approval = ActionApproval(
        id=uid(),
        subject=subject,
        action=action,
        service_name=service,
        fault_id=fault_id,
        approved_by=getpass.getuser()[:120],
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )
    approval.signature = grant_signature(approval, settings.approval_key.get_secret_value())
    session.add(approval)
    session.flush()
    session.add(
        GatewayAudit(
            request_id=uid(),
            subject=subject,
            tool=action,
            service_name=service,
            outcome="human_approved",
            approval_id=approval.id,
        )
    )
    return approval.id
