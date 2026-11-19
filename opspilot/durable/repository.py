"""Durable run/intent creation and append-only attempt timeline."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from opspilot.agent.schemas import InvestigationState
from opspilot.durable.contracts import ExecutionError, VerificationPlan
from opspilot.durable.evidence import check_evidence_content
from opspilot.durable.policy import (
    approval_dict,
    audit,
    check_integrity,
    current_preconditions,
    effective_state,
    fingerprint,
)
from opspilot.gateway.contracts import ACTION_TOOLS
from opspilot.gateway.security import canonical
from opspilot.models import (
    DurableAttempt,
    DurableAudit,
    DurableRun,
    GatewayAudit,
    Incident,
    RemediationApproval,
    now,
)


class Repository:
    def __init__(self, engine):
        self.engine = engine

    def submit(self, investigation, plan=None, ttl=300, recovery_of=None):
        result = InvestigationState.model_validate(investigation)
        plan = plan or VerificationPlan()
        if (
            result.run_status != "completed"
            or not result.proposed_remediation
            or result.proposed_remediation.action not in ACTION_TOOLS
            or not result.candidate_root_cause
            or not 30 <= ttl <= 600
        ):
            raise ExecutionError("UNSUPPORTED_RECOMMENDATION")
        snapshot = result.model_dump(mode="json")
        if len(canonical(snapshot)) > 262144:
            raise ExecutionError("INVESTIGATION_TOO_LARGE")
        input_digest = hashlib.sha256(
            canonical(
                {
                    "investigation": snapshot,
                    "verification_plan": plan.model_dump(),
                    "recovery_of": recovery_of,
                }
            )
        ).hexdigest()
        run_id = str(result.run_id)
        with Session(self.engine) as session, session.begin():
            old = session.get(DurableRun, run_id)
            if old:
                if old.input_digest != input_digest:
                    raise ExecutionError("RUN_INPUT_MISMATCH")
                audit(session, run_id, "duplicate_submission")
                return self._request(session, run_id).id
            if recovery_of:
                parent = session.get(DurableRun, str(UUID(recovery_of)))
                if (
                    not parent
                    or parent.status not in {"failed", "inconclusive"}
                    or parent.action_result is None
                ):
                    raise ExecutionError("RECOVERY_NOT_AUTHORIZED_BY_POLICY")
            service = result.proposed_remediation.service_name.value
            incident = session.get(Incident, str(result.incident_id))
            if not incident:
                raise ExecutionError("INCIDENT_NOT_FOUND")
            # This is a proposal, not authority. Resource versions are revalidated by the
            # human issuer and atomically under backend service locks at execution.
            preconditions = current_preconditions(
                session, incident.id, service, result.proposed_remediation.action
            )
            # Retain cited operational observations, not unbounded model prose or secrets.
            refs = set(result.proposed_remediation.evidence_refs)
            if not refs or not refs <= {o.id for o in result.observations}:
                raise ExecutionError("INVALID_EVIDENCE")
            evidence = {
                "references": sorted(refs),
                "observations": [
                    o.model_dump(mode="json") for o in result.observations if o.id in refs
                ],
                "mode": result.mode,
            }
            # Imported recommendations must cite real successful diagnostic calls and the
            # current incident/target metric windows, rather than fabricated fixture reports.
            serialized = canonical(evidence).decode()
            if not all(
                metric_id in serialized for metric_id in preconditions["metric_ids"].values()
            ):
                raise ExecutionError("STALE_OR_MISSING_EVIDENCE")
            for observation in result.observations:
                if observation.id not in refs:
                    continue
                check_evidence_content(session, observation)
                proof = session.scalar(
                    select(GatewayAudit).where(GatewayAudit.request_id == observation.request_id)
                )
                if (
                    not proof
                    or proof.outcome != "success"
                    or proof.tool != observation.tool_name
                    or proof.service_name != observation.service_name
                ):
                    raise ExecutionError("UNATTESTED_EVIDENCE")
            session.add(
                DurableRun(
                    id=run_id,
                    incident_id=incident.id,
                    service_name=service,
                    investigation=snapshot,
                    input_digest=input_digest,
                    recovery_of=recovery_of,
                    status="awaiting_approval",
                )
            )
            session.flush()
            approval_id = str(uuid4())
            values = {
                "id": approval_id,
                "run_id": run_id,
                "incident_id": incident.id,
                "tool": result.proposed_remediation.action,
                "service_name": service,
                "arguments": {
                    "service_name": service,
                    "approval_id": approval_id,
                    "request_id": str(uuid5(result.run_id, "sandbox-action-v1")),
                    "run_id": run_id,
                },
                "risk": "medium",
                "evidence": evidence,
                "preconditions": preconditions,
                "verification_plan": plan.model_dump(),
                "expires_at": datetime.now(UTC) + timedelta(seconds=ttl),
                "created_at": now(),
            }
            values["fingerprint"] = fingerprint(values)
            values["arguments"]["action_fingerprint"] = values["fingerprint"]
            # Explicit columns: runner has no INSERT/UPDATE permission on human decision fields.
            session.execute(insert(RemediationApproval).values(**values))
            audit(
                session,
                run_id,
                "approval_requested",
                {
                    "approval_id": approval_id,
                    "fingerprint": values["fingerprint"],
                    "recovery_of": recovery_of,
                },
            )
            return approval_id

    @staticmethod
    def _request(session, run_id):
        row = session.scalar(
            select(RemediationApproval).where(RemediationApproval.run_id == run_id)
        )
        if not row:
            raise ExecutionError("RUN_NOT_FOUND")
        check_integrity(row)
        return row

    def request(self, run_id):
        with Session(self.engine) as session:
            row = self._request(session, run_id)
            session.expunge(row)
            return row

    def request_by_id(self, approval_id):
        with Session(self.engine) as session:
            row = session.get(RemediationApproval, approval_id)
            if not row:
                raise ExecutionError("APPROVAL_NOT_FOUND")
            check_integrity(row)
            session.expunge(row)
            return row

    def event(self, run_id, kind, detail=None):
        with Session(self.engine) as session, session.begin():
            audit(session, run_id, kind, detail)

    def update(self, run_id, **values):
        with Session(self.engine) as session, session.begin():
            row = session.get(DurableRun, run_id)
            if not row:
                raise ExecutionError("RUN_NOT_FOUND")
            for key, value in values.items():
                if key not in {"status", "action_result", "verification"}:
                    raise ValueError("unsupported run update")
                setattr(row, key, value)
            row.updated_at = now()

    def attempt(self, run_id, request_id, kind):
        with Session(self.engine) as session, session.begin():
            row = DurableAttempt(
                run_id=run_id, request_id=request_id, kind=kind, outcome="prepared"
            )
            session.add(row)
            session.flush()
            audit(
                session,
                run_id,
                "attempt_prepared",
                {"attempt_id": row.id, "kind": kind, "request_id": request_id},
            )
            return row.id

    def finish_attempt(self, attempt_id, outcome):
        with Session(self.engine) as session, session.begin():
            row = session.get(DurableAttempt, attempt_id)
            row.outcome, row.finished_at = outcome, now()
            audit(
                session, row.run_id, "attempt_" + outcome, {"attempt_id": row.id, "kind": row.kind}
            )

    def reconcile_attempts(self, run_id, kind):
        with Session(self.engine) as session, session.begin():
            rows = session.scalars(
                select(DurableAttempt).where(
                    DurableAttempt.run_id == run_id,
                    DurableAttempt.kind == kind,
                    DurableAttempt.outcome.in_(["prepared", "uncertain"]),
                )
            )
            for row in rows:
                row.outcome, row.finished_at = "reconciled", now()
                audit(session, run_id, "attempt_reconciled", {"attempt_id": row.id, "kind": kind})

    def attempt_count(self, run_id, kind):
        from sqlalchemy import func

        with Session(self.engine) as session:
            return session.scalar(
                select(func.count())
                .select_from(DurableAttempt)
                .where(DurableAttempt.run_id == run_id, DurableAttempt.kind == kind)
            )

    def report(self, run_id, limit=None):
        with Session(self.engine) as session:
            request = self._request(session, run_id)
            run = session.get(DurableRun, run_id)
            timeline = [
                {
                    "sequence": e.id,
                    "at": e.created_at.isoformat(),
                    "actor": e.actor,
                    "kind": e.kind,
                    "detail": e.detail,
                }
                for e in session.scalars(
                    select(DurableAudit)
                    .where(DurableAudit.run_id == run_id)
                    .order_by(DurableAudit.id)
                    .limit(limit + 1 if limit else None)
                )
            ]
            gateway = [
                {
                    "request_id": e.request_id,
                    "tool": e.tool,
                    "outcome": e.outcome,
                    "at": e.created_at.isoformat(),
                }
                for e in session.scalars(
                    select(GatewayAudit)
                    .where(GatewayAudit.approval_id == request.id)
                    .order_by(GatewayAudit.created_at, GatewayAudit.id)
                    .limit(limit + 1 if limit else None)
                )
            ]
            return {
                "run_id": run.id,
                "thread_id": run.id,
                "status": run.status,
                "incident_id": run.incident_id,
                "investigation_mode": run.investigation["mode"],
                "recovery_of": run.recovery_of,
                "approval": {
                    **approval_dict(request),
                    "expires_at": request.expires_at.isoformat(),
                    "id": request.id,
                    "fingerprint": request.fingerprint,
                    "state": effective_state(request),
                    "approved_by": request.approved_by,
                    "revoked_by": request.revoked_by,
                },
                "action_result": run.action_result,
                "verification": run.verification,
                "timeline": timeline[:limit],
                "gateway_audit": gateway[:limit],
                "complete_audit_timeline": sorted(
                    [{"source": "workflow", **event} for event in timeline[:limit]]
                    + [{"source": "gateway", **event} for event in gateway[:limit]],
                    key=lambda event: event["at"],
                ),
                "timeline_truncated": bool(
                    limit and (len(timeline) > limit or len(gateway) > limit)
                ),
            }
