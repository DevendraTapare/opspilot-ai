"""Trusted backend reconciliation and one-time approved verification workload."""

from opspilot.agent.evidence import METRIC_FIELDS, pick
from opspilot.durable.contracts import VerificationPlan
from opspilot.durable.policy import audit, bound_request
from opspilot.faults import lock_services
from opspilot.gateway.contracts import ActionData, ErrorCode, ExecutionStatus, GatewayError
from opspilot.models import ActionExecution, RemediationVerification
from opspilot.observability import observed
from opspilot.schemas import MetricOut, WorkloadRequest
from opspilot.telemetry import execute_workload


def execution_status(session, caller, args):
    request = bound_request(session, caller, args)
    execution = session.get(ActionExecution, str(args.request_id))
    verification = session.get(RemediationVerification, str(args.request_id))
    result = None
    if execution:
        if (
            execution.approval_id != request.id
            or execution.subject != caller.subject
            or execution.service_name != request.service_name
            or execution.action != request.tool
        ):
            raise GatewayError(ErrorCode.APPROVAL_INVALID)
        result = ActionData(
            action=execution.action,
            service_name=execution.service_name,
            fault_id=execution.fault_id,
            approval_id=execution.approval_id,
            execution_id=execution.request_id,
        )
    return ExecutionStatus(
        run_id=request.run_id,
        request_id=args.request_id,
        committed=execution is not None,
        action_result=result,
        verification=verification.result if verification else None,
    )


@observed("remediation.verification")
def verify_remediation(session, caller, args):
    request = bound_request(session, caller, args)
    root_service = request.preconditions["incident_service"]
    # Same service locks as the actual workload, before checking the unique verification ledger.
    names = (
        ["checkout-service", "payment-service", "inventory-service"]
        if (root_service == "checkout-service")
        else [root_service, request.service_name]
    )
    lock_services(session, sorted(set(names)))
    status = execution_status(session, caller, args)
    if not status.committed or request.state != "consumed":
        raise GatewayError(ErrorCode.APPROVAL_REQUIRED)
    if status.verification:
        return status.verification
    # Verification is authorized with the original action, even if its execution TTL has elapsed.
    plan = VerificationPlan.model_validate(request.verification_plan)
    workload = execute_workload(
        session,
        root_service,
        WorkloadRequest(count=plan.count, arrival_interval_ms=plan.arrival_interval_ms),
    )
    metrics = [
        pick(MetricOut.model_validate(m).model_dump(mode="json"), METRIC_FIELDS)
        for m in workload["metrics"]
    ]
    relevant = [m for m in metrics if m["service_name"] in {root_service, request.service_name}]
    if not {root_service, request.service_name} <= {m["service_name"] for m in relevant}:
        outcome = "inconclusive"
    else:
        outcome = (
            "verified"
            if all(
                m["requests"] > 0
                and m["error_rate"] <= plan.max_error_rate
                and m["p95_latency_ms"] <= plan.max_p95_latency_ms
                for m in relevant
            )
            else "failed"
        )
    result = {
        "run_id": request.run_id,
        "request_id": str(args.request_id),
        "outcome": outcome,
        "workload_run_id": workload["run_id"],
        "metrics": metrics,
        "recovery_requires_new_approval": outcome != "verified",
    }
    # Metric/log/incident updates and this unique result commit in the same DB transaction.
    session.add(
        RemediationVerification(
            request_id=str(args.request_id), run_id=request.run_id, result=result
        )
    )
    audit(
        session,
        request.run_id,
        "verification_" + outcome,
        {"request_id": str(args.request_id), "workload_run_id": workload["run_id"]},
    )
    return result
