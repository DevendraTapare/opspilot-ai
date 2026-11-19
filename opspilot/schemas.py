from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ServiceName(StrEnum):
    CHECKOUT = "checkout-service"
    PAYMENT = "payment-service"
    INVENTORY = "inventory-service"


class ScenarioId(StrEnum):
    SLOW_CHECKOUT = "slow-checkout"
    PAYMENT_UNAVAILABLE = "payment-unavailable"
    INVENTORY_DB_EXHAUSTION = "inventory-db-exhaustion"
    WORKER_SATURATION = "worker-saturation"
    BAD_CONFIG = "bad-config"


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def utc_timestamp(cls, value):
        # SQLite drops timezone metadata; both backends represent these values as UTC.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class FaultCreate(InputModel):
    service_name: ServiceName
    scenario_id: ScenarioId

    # JSON enum values should accept strings; other fields remain strict.
    model_config = ConfigDict(extra="forbid", strict=False)

    @model_validator(mode="after")
    def valid_target(self):
        targets = {
            ScenarioId.SLOW_CHECKOUT: {ServiceName.CHECKOUT},
            ScenarioId.PAYMENT_UNAVAILABLE: {ServiceName.PAYMENT},
            ScenarioId.INVENTORY_DB_EXHAUSTION: {ServiceName.INVENTORY},
            ScenarioId.WORKER_SATURATION: set(ServiceName),
            ScenarioId.BAD_CONFIG: {ServiceName.CHECKOUT},
        }
        if self.service_name not in targets[self.scenario_id]:
            raise ValueError("scenario is not supported by the selected service")
        return self


class FaultOut(OutputModel):
    id: UUID
    service_name: ServiceName
    scenario_id: ScenarioId
    active: bool
    created_at: datetime
    deactivated_at: datetime | None


class ScenarioOut(BaseModel):
    scenario_id: str
    services: list[ServiceName]
    effect: str


class ResetRequest(InputModel):
    services: Annotated[list[ServiceName], Field(min_length=1, max_length=3)]
    seed: Annotated[int, Field(ge=0, le=2_147_483_647, strict=True)] = 42

    model_config = ConfigDict(extra="forbid", strict=False)

    @model_validator(mode="after")
    def unique_services(self):
        if len(set(self.services)) != len(self.services):
            raise ValueError("services must be explicitly selected without duplicates")
        return self


class ServiceOut(OutputModel):
    name: ServiceName
    description: str
    seed: int
    cursor: int
    generation: int


class ResetOut(BaseModel):
    scenario_id: Literal["healthy-baseline"] = "healthy-baseline"
    reset_services: list[ServiceOut]
    deactivated_fault_ids: list[UUID]
    resolved_incident_ids: list[UUID]


class WorkloadRequest(InputModel):
    count: Annotated[int, Field(ge=1, le=50)] = 12
    arrival_interval_ms: Annotated[int, Field(ge=0, le=100)] = 25


class SampleOut(BaseModel):
    service_name: ServiceName
    request_index: int
    status_code: int
    latency_ms: float
    code: str


class MetricOut(OutputModel):
    id: UUID
    run_id: UUID
    service_name: ServiceName
    incident_id: UUID | None
    fault_id: UUID | None
    scenario_id: str
    generation: int
    seed: int
    requests: int
    errors: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    worker_utilization: float
    db_pool_utilization: float
    window_ms: float
    status_counts: dict[str, int]
    created_at: datetime


class WorkloadOut(BaseModel):
    run_id: UUID
    service_name: ServiceName
    simulated_window_ms: float
    results: list[SampleOut]
    metrics: list[MetricOut]


class IncidentOut(OutputModel):
    id: UUID
    service_name: ServiceName
    status: Literal["open", "resolved"]
    title: str
    scenario_id: str | None
    fault_id: UUID | None
    opened_at: datetime
    resolved_at: datetime | None


class EventOut(OutputModel):
    id: UUID
    incident_id: UUID
    kind: str
    detail: dict
    created_at: datetime


class LogOut(OutputModel):
    id: UUID
    run_id: UUID
    service_name: ServiceName
    incident_id: UUID | None
    fault_id: UUID | None
    request_index: int
    level: str
    code: str
    status_code: int
    latency_ms: float
    created_at: datetime


class DeploymentOut(OutputModel):
    id: UUID
    service_name: ServiceName
    fault_id: UUID | None
    scenario_id: str
    kind: str
    config: dict
    created_at: datetime


class HealthOut(BaseModel):
    status: str


class IncidentDetail(IncidentOut):
    events: list[EventOut]
