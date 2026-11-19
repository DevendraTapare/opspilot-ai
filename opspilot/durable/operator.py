"""Authenticated human decisions shared by the terminal and local dashboard API."""

import argparse
import getpass
import hashlib
import hmac
import json
import sys
from datetime import UTC, datetime
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.db import make_engine
from opspilot.durable.contracts import ExecutionError, HumanOperator
from opspilot.durable.policy import audit, check_integrity, current_preconditions, effective_state
from opspilot.gateway.approvals import ACTION_SCENARIOS, grant_signature
from opspilot.models import ActionApproval, RemediationApproval
from opspilot.observability import attributes, observed


def authenticate_operator(registry: str, token: str) -> HumanOperator:
    if not 32 <= len(token) <= 256:
        raise ExecutionError("OPERATOR_AUTHENTICATION_FAILED")
    entries = json.loads(registry)
    if not isinstance(entries, list) or not 1 <= len(entries) <= 16:
        raise ExecutionError("OPERATOR_CONFIGURATION_INVALID")
    digest = hashlib.sha256(token.encode()).hexdigest()
    for entry in entries:
        principal = HumanOperator.model_validate(entry)
        if not principal.actions or not principal.actions <= set(ACTION_SCENARIOS):
            raise ExecutionError("OPERATOR_CONFIGURATION_INVALID")
        if hmac.compare_digest(principal.token_sha256, digest) and (
            principal.os_user.casefold() == getpass.getuser().casefold()
        ):
            return principal
    raise ExecutionError("OPERATOR_AUTHENTICATION_FAILED")


@observed("approval.human_transition_attempt")
def decide_interactively(engine, settings, registry, approval_id, decision):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ExecutionError("INTERACTIVE_HUMAN_REQUIRED")
    principal = authenticate_operator(registry, getpass.getpass("Operator credential: "))
    if decision not in {"approve", "revoke"}:
        raise ExecutionError("INVALID_OPERATOR_DECISION")
    with Session(engine) as session:
        request = session.get(RemediationApproval, approval_id)
        if not request:
            raise ExecutionError("APPROVAL_NOT_FOUND")
        check_integrity(request)
        if request.service_name not in principal.services or request.tool not in principal.actions:
            with session.begin_nested():
                audit(session, request.run_id, "operator_scope_denied", actor=principal.subject)
            session.commit()
            raise ExecutionError("OPERATOR_FORBIDDEN")
        reviewed_fingerprint = request.fingerprint
        audit(
            session,
            request.run_id,
            "human_review_started",
            {"approval_id": request.id, "decision": decision, "fingerprint": reviewed_fingerprint},
            principal.subject,
        )
        session.commit()
        # Display exact arguments and verification plan, including all bound evidence.
        from opspilot.durable.repository import Repository

        print(json.dumps(Repository(engine).report(request.run_id)["approval"], indent=2))
        phrase = f"{decision.upper()} {reviewed_fingerprint}"
        if input(f"Type exactly '{phrase}': ") != phrase:
            raise ExecutionError("OPERATOR_CANCELLED")
    # Do not hold locks during human review; reacquire and revalidate before signing.
    return decide_authorized(
        engine, settings, principal, approval_id, decision, reviewed_fingerprint
    )


@observed("approval.authenticated_human_decision")
def decide_authorized(engine, settings, principal, approval_id, decision, reviewed_fingerprint):
    """Trusted callers supply an authenticated principal, never a client-selected identity."""
    if not isinstance(principal, HumanOperator) or decision not in {"approve", "revoke"}:
        raise ExecutionError("OPERATOR_FORBIDDEN")
    with Session(engine) as session, session.begin():
        grant = session.scalar(select(ActionApproval).where(ActionApproval.id == approval_id))
        request = session.scalar(
            select(RemediationApproval)
            .where(RemediationApproval.id == approval_id)
            .with_for_update()
        )
        if not request:
            raise ExecutionError("APPROVAL_NOT_FOUND")
        check_integrity(request)
        if request.service_name not in principal.services or request.tool not in principal.actions:
            raise ExecutionError("OPERATOR_FORBIDDEN")
        run_id, service = request.run_id, request.service_name
        if not hmac.compare_digest(reviewed_fingerprint, request.fingerprint):
            raise ExecutionError("APPROVAL_MODIFIED")
        state = effective_state(request)
        if decision == "revoke":
            if state not in {"pending", "approved"}:
                raise ExecutionError("APPROVAL_NOT_REVOCABLE")
            request.state, request.revoked_by = "revoked", principal.subject
            request.revoked_at = datetime.now(UTC)
        else:
            if state != "pending" or grant:
                raise ExecutionError("APPROVAL_ALREADY_DECIDED_OR_EXPIRED")
            if (
                current_preconditions(session, request.incident_id, service, request.tool)
                != request.preconditions
            ):
                raise ExecutionError("STALE_INCIDENT_OR_RESOURCE")
            grant = ActionApproval(
                id=request.id,
                subject="durable-executor",
                action=request.tool,
                service_name=service,
                fault_id=request.preconditions["fault_id"],
                approved_by=principal.subject,
                expires_at=request.expires_at,
                durable_request_id=request.id,
                durable_fingerprint=request.fingerprint,
            )
            grant.signature = grant_signature(grant, settings.approval_key.get_secret_value())
            session.add(grant)
            request.state, request.approved_by = "approved", principal.subject
            request.approved_at = datetime.now(UTC)
        audit(
            session,
            run_id,
            "human_" + decision + "d",
            {"approval_id": request.id, "fingerprint": request.fingerprint},
            principal.subject,
        )
        attributes(**{"opspilot.run_id": run_id, "opspilot.status": request.state})
    return approval_id


class OperatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_OPERATOR_", env_file=".operator.env", extra="ignore"
    )
    database_url: SecretStr
    approval_key: SecretStr
    operators: SecretStr


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decision", choices=["approve", "revoke"])
    parser.add_argument("--approval-id", type=UUID, required=True)
    args = parser.parse_args()
    # Operator environment is separate from worker environment; no general .env fallback.
    settings = OperatorSettings()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        decide_interactively(
            engine,
            settings,
            settings.operators.get_secret_value(),
            str(args.approval_id),
            args.decision,
        )
        print("Operator decision persisted.")
    except Exception:
        print("Operator decision rejected; no approval was issued.", file=sys.stderr)
        raise SystemExit(2) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
