from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DashboardRun(Base):
    __tablename__ = "dashboard_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"
    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Service(Base):
    __tablename__ = "services"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(160))
    seed: Mapped[int] = mapped_column(Integer, default=42)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)


class Fault(Base):
    __tablename__ = "faults"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_fault_active_service",
            "service_name",
            unique=True,
            postgresql_where=text("active = true"),
            sqlite_where=text("active = 1"),
        ),
    )


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    title: Mapped[str] = mapped_column(String(160))
    scenario_id: Mapped[str | None] = mapped_column(String(50))
    fault_id: Mapped[str | None] = mapped_column(ForeignKey("faults.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_incident_open_service",
            "service_name",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"), index=True)
    fault_id: Mapped[str | None] = mapped_column(ForeignKey("faults.id"))
    scenario_id: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(40))
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MetricSummary(Base):
    __tablename__ = "metric_summaries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"), index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    fault_id: Mapped[str | None] = mapped_column(ForeignKey("faults.id"))
    scenario_id: Mapped[str] = mapped_column(String(50))
    generation: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    requests: Mapped[int] = mapped_column(Integer)
    errors: Mapped[int] = mapped_column(Integer)
    error_rate: Mapped[float] = mapped_column(Float)
    avg_latency_ms: Mapped[float] = mapped_column(Float)
    p95_latency_ms: Mapped[float] = mapped_column(Float)
    max_latency_ms: Mapped[float] = mapped_column(Float)
    worker_utilization: Mapped[float] = mapped_column(Float)
    db_pool_utilization: Mapped[float] = mapped_column(Float)
    window_ms: Mapped[float] = mapped_column(Float)
    status_counts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SimulationLog(Base):
    __tablename__ = "simulation_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"), index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    fault_id: Mapped[str | None] = mapped_column(ForeignKey("faults.id"))
    request_index: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(50))
    status_code: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActionApproval(Base):
    __tablename__ = "action_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(50))
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"))
    fault_id: Mapped[str] = mapped_column(ForeignKey("faults.id"))
    approved_by: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signature: Mapped[str] = mapped_column(String(64))
    consumed_by: Mapped[str | None] = mapped_column(String(36))
    durable_request_id: Mapped[str | None] = mapped_column(String(36))
    durable_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActionExecution(Base):
    __tablename__ = "action_executions"
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("action_approvals.id"), unique=True)
    subject: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(50))
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"))
    fault_id: Mapped[str] = mapped_column(ForeignKey("faults.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GatewayAudit(Base):
    __tablename__ = "gateway_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    subject: Mapped[str] = mapped_column(String(40), index=True)
    tool: Mapped[str] = mapped_column(String(50))
    service_name: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(40))
    approval_id: Mapped[str | None] = mapped_column(String(36))
    action_request_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DurableRun(Base):
    __tablename__ = "durable_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"))
    investigation: Mapped[dict] = mapped_column(JSON)
    input_digest: Mapped[str] = mapped_column(String(64))
    recovery_of: Mapped[str | None] = mapped_column(ForeignKey("durable_runs.id"))
    status: Mapped[str] = mapped_column(String(40), default="awaiting_approval")
    action_result: Mapped[dict | None] = mapped_column(JSON)
    verification: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RemediationApproval(Base):
    __tablename__ = "remediation_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("durable_runs.id"), unique=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    tool: Mapped[str] = mapped_column(String(50))
    arguments: Mapped[dict] = mapped_column(JSON)
    service_name: Mapped[str] = mapped_column(ForeignKey("services.name"))
    risk: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[dict] = mapped_column(JSON)
    preconditions: Mapped[dict] = mapped_column(JSON)
    verification_plan: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), server_default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(120), server_default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(120))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DurableAttempt(Base):
    __tablename__ = "durable_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("durable_runs.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RemediationVerification(Base):
    __tablename__ = "remediation_verifications"
    request_id: Mapped[str] = mapped_column(
        ForeignKey("action_executions.request_id"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("durable_runs.id"), unique=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DurableAudit(Base):
    __tablename__ = "durable_audit_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("durable_runs.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
