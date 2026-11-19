import secrets
import time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opspilot import faults
from opspilot.models import (
    DeploymentEvent,
    Fault,
    Incident,
    IncidentEvent,
    MetricSummary,
    Service,
    SimulationLog,
)
from opspilot.schemas import (
    DeploymentOut,
    EventOut,
    FaultCreate,
    FaultOut,
    HealthOut,
    IncidentDetail,
    IncidentOut,
    LogOut,
    MetricOut,
    ResetOut,
    ResetRequest,
    ScenarioOut,
    ServiceName,
    ServiceOut,
    WorkloadOut,
    WorkloadRequest,
)
from opspilot.telemetry import execute_workload

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def control_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = request.app.state.settings.control_token.get_secret_value()
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(
            401, "Valid control bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )


CONTROL = [Depends(control_access)]


@router.get("/health/live", response_model=HealthOut, tags=["health"])
def live():
    return {"status": "alive"}


@router.get("/health/ready", response_model=HealthOut, tags=["health"])
def ready(db: DB):
    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        count = db.scalar(select(func.count()).select_from(Service))
        if revision != "0004_dashboard" or count != 3:
            raise HTTPException(503, "Database migration or service fixtures are not ready")
    except SQLAlchemyError:
        raise HTTPException(503, "Database is not ready") from None
    return {"status": "ready"}


@router.get("/api/v1/services", response_model=list[ServiceOut], tags=["services"])
def services(db: DB):
    return list(db.scalars(select(Service).order_by(Service.name)))


@router.get("/api/v1/scenarios", response_model=list[ScenarioOut], tags=["faults"])
def scenarios():
    return faults.SCENARIOS


@router.get("/api/v1/faults", response_model=list[FaultOut], tags=["faults"])
def list_faults(
    db: DB,
    service_name: ServiceName | None = None,
    active: bool | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
):
    statement = select(Fault)
    if service_name:
        statement = statement.where(Fault.service_name == service_name)
    if active is not None:
        statement = statement.where(Fault.active == active)
    return list(
        db.scalars(statement.order_by(Fault.created_at, Fault.id).limit(limit).offset(offset))
    )


@router.post(
    "/api/v1/faults",
    response_model=FaultOut,
    status_code=201,
    dependencies=CONTROL,
    tags=["faults"],
)
def create_fault(body: FaultCreate, db: DB):
    with db.begin():
        fault = faults.activate(db, body)
    return fault


@router.post(
    "/api/v1/faults/{fault_id}/deactivate",
    response_model=FaultOut,
    dependencies=CONTROL,
    tags=["faults"],
)
def deactivate_fault(fault_id: UUID, db: DB):
    with db.begin():
        fault = db.get(Fault, str(fault_id))
        if fault is None:
            raise HTTPException(404, "Fault not found")
        faults.lock_services(db, [fault.service_name])
        # Refresh after taking the service lock; concurrent resets may have deactivated it.
        db.refresh(fault)
        if fault.active:
            faults.deactivate(db, fault)
    return fault


@router.post(
    "/api/v1/fixtures/reset",
    response_model=ResetOut,
    dependencies=CONTROL,
    tags=["fixtures"],
)
def reset_fixtures(body: ResetRequest, db: DB):
    with db.begin():
        result = faults.reset(db, body)
    return result


def replay_window(milliseconds: float) -> None:
    time.sleep(milliseconds / 1000)


def run_workload(service_name: ServiceName, body: WorkloadRequest, db: Session) -> dict:
    with db.begin():
        result = execute_workload(db, service_name, body)
    # Replay the virtual burst window. Values above are derived from simulated execution,
    # not from host timing, so CI scheduling does not change seeded scenario outputs.
    replay_window(result["simulated_window_ms"])
    return result


@router.post(
    "/api/v1/simulator/{service_name}/workloads",
    response_model=WorkloadOut,
    dependencies=CONTROL,
    tags=["simulator"],
)
def workload(service_name: ServiceName, body: WorkloadRequest, db: DB):
    return run_workload(service_name, body, db)


@router.post(
    "/api/v1/simulator/{service_name}/request",
    response_model=WorkloadOut,
    dependencies=CONTROL,
    tags=["simulator"],
    responses={
        500: {"description": "Simulated bad configuration"},
        502: {"description": "Simulated dependency failed"},
        503: {"description": "Simulated resource or dependency unavailable"},
    },
)
def single_request(service_name: ServiceName, db: DB, response: Response):
    result = run_workload(service_name, WorkloadRequest(count=1, arrival_interval_ms=0), db)
    response.status_code = result["results"][0]["status_code"]
    return result


@router.get("/api/v1/incidents", response_model=list[IncidentOut], tags=["incidents"])
def list_incidents(
    db: DB,
    service_name: ServiceName | None = None,
    status: Literal["open", "resolved"] | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
):
    statement = select(Incident)
    if service_name:
        statement = statement.where(Incident.service_name == service_name)
    if status:
        statement = statement.where(Incident.status == status)
    return list(
        db.scalars(statement.order_by(Incident.opened_at, Incident.id).limit(limit).offset(offset))
    )


def require_incident(db: Session, incident_id: UUID) -> Incident:
    incident = db.get(Incident, str(incident_id))
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return incident


@router.get("/api/v1/incidents/{incident_id}", response_model=IncidentDetail, tags=["incidents"])
def get_incident(incident_id: UUID, db: DB):
    incident = require_incident(db, incident_id)
    events = list(
        db.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == str(incident_id))
            .order_by(IncidentEvent.created_at, IncidentEvent.id)
        )
    )
    return IncidentDetail(
        **IncidentOut.model_validate(incident).model_dump(),
        events=[EventOut.model_validate(event) for event in events],
    )


@router.get(
    "/api/v1/incidents/{incident_id}/metrics", response_model=list[MetricOut], tags=["telemetry"]
)
def incident_metrics(incident_id: UUID, db: DB, limit: Limit = 100, offset: Offset = 0):
    require_incident(db, incident_id)
    return list(
        db.scalars(
            select(MetricSummary)
            .where(MetricSummary.incident_id == str(incident_id))
            .order_by(MetricSummary.created_at, MetricSummary.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/api/v1/incidents/{incident_id}/logs", response_model=list[LogOut], tags=["telemetry"])
def incident_logs(incident_id: UUID, db: DB, limit: Limit = 100, offset: Offset = 0):
    require_incident(db, incident_id)
    return list(
        db.scalars(
            select(SimulationLog)
            .where(SimulationLog.incident_id == str(incident_id))
            .order_by(SimulationLog.created_at, SimulationLog.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get(
    "/api/v1/services/{service_name}/metrics", response_model=list[MetricOut], tags=["telemetry"]
)
def service_metrics(service_name: ServiceName, db: DB, limit: Limit = 100, offset: Offset = 0):
    return list(
        db.scalars(
            select(MetricSummary)
            .where(MetricSummary.service_name == service_name)
            .order_by(MetricSummary.created_at, MetricSummary.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/api/v1/services/{service_name}/logs", response_model=list[LogOut], tags=["telemetry"])
def service_logs(service_name: ServiceName, db: DB, limit: Limit = 100, offset: Offset = 0):
    return list(
        db.scalars(
            select(SimulationLog)
            .where(SimulationLog.service_name == service_name)
            .order_by(SimulationLog.created_at, SimulationLog.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get(
    "/api/v1/services/{service_name}/deployments",
    response_model=list[DeploymentOut],
    tags=["deployments"],
)
def deployments(service_name: ServiceName, db: DB, limit: Limit = 100, offset: Offset = 0):
    return list(
        db.scalars(
            select(DeploymentEvent)
            .where(DeploymentEvent.service_name == service_name)
            .order_by(DeploymentEvent.created_at, DeploymentEvent.id)
            .limit(limit)
            .offset(offset)
        )
    )
