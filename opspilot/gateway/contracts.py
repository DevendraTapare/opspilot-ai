import json
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opspilot.schemas import DeploymentOut, IncidentOut, LogOut, MetricOut, ServiceName

MAX_ARGUMENT_BYTES = 4096
MAX_RESULT_BYTES = 32768
MAX_HTTP_BYTES = 16384
PROTOCOL_VERSION = "2026-07-28"


class ErrorCode(StrEnum):
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    ACTIONS_DISABLED = "ACTIONS_DISABLED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    APPROVAL_USED = "APPROVAL_USED"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    STALE_APPROVAL = "STALE_APPROVAL"
    DOWNSTREAM_UNAVAILABLE = "DOWNSTREAM_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"


class GatewayError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ServiceInput(StrictInput):
    service_name: ServiceName


class PageInput(ServiceInput):
    limit: Annotated[int, Field(ge=1, le=20)] = 10
    offset: Annotated[int, Field(ge=0, le=10000)] = 0


class IncidentListInput(PageInput):
    status: Literal["open", "resolved"] | None = None


class IncidentInput(ServiceInput):
    incident_id: UUID
    event_limit: Annotated[int, Field(ge=1, le=20)] = 10


class LogSearchInput(PageInput):
    query: Annotated[str, Field(max_length=128)] = ""
    level: Literal["INFO", "ERROR"] | None = None


class ActionInput(ServiceInput):
    approval_id: UUID | None = None
    request_id: UUID
    run_id: UUID | None = None
    action_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class DurableInput(ActionInput):
    approval_id: UUID
    run_id: UUID
    action_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DenialInput(StrictInput):
    tool: Annotated[str, Field(max_length=50)]
    service_name: ServiceName | None = None
    outcome: ErrorCode

    @model_validator(mode="after")
    def only_allowlisted_names(self):
        if self.tool not in TOOLS and self.tool != "unknown_tool":
            raise ValueError("invalid tool")
        return self


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False


class ToolResponse[T](BaseModel):
    ok: bool
    request_id: UUID
    data: T | None = None
    error: ErrorDetail | None = None
    source: Literal["opspilot-simulator"] = "opspilot-simulator"
    untrusted_data: Literal[True] = True

    @model_validator(mode="after")
    def explicit_state(self):
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("successful responses need data and no error")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("failed responses need an error and no data")
        return self


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    next_offset: int | None


class EventData(BaseModel):
    id: UUID
    kind: str
    created_at: str
    # Bounded observation values only; arbitrary event payloads are not relayed.
    metric_id: UUID | None = None
    run_id: UUID | None = None


class IncidentData(BaseModel):
    incident: IncidentOut
    events: list[EventData]
    events_truncated: bool


class HealthData(BaseModel):
    service_name: ServiceName
    status: Literal["unknown", "healthy", "degraded"]
    evidence: Literal["no_observations", "latest_metric_window"]
    observed_at: str | None
    active_fault: str | None
    metric: MetricOut | None


class MetricPage(BaseModel):
    items: list[MetricOut]
    next_offset: int | None


class LogPage(BaseModel):
    items: list[LogOut]
    next_offset: int | None


class DeploymentPage(BaseModel):
    items: list[DeploymentOut]
    next_offset: int | None


class DependencyData(BaseModel):
    service_name: ServiceName
    dependencies: list[HealthData]


class ActionData(BaseModel):
    action: str
    service_name: ServiceName
    fault_id: UUID
    approval_id: UUID
    execution_id: UUID
    effect: Literal["matching_simulated_fault_deactivated"] = "matching_simulated_fault_deactivated"


class VerificationResult(BaseModel):
    run_id: UUID
    request_id: UUID
    outcome: Literal["verified", "failed", "inconclusive"]
    workload_run_id: UUID
    metrics: Annotated[list[dict], Field(max_length=3)]
    recovery_requires_new_approval: bool


class ExecutionStatus(BaseModel):
    run_id: UUID
    request_id: UUID
    committed: bool
    action_result: ActionData | None
    verification: VerificationResult | None


# This immutable, explicitly named registry is the only dispatch surface.
READ_TOOLS = {
    "list_incidents": (IncidentListInput, IncidentPage),
    "get_incident": (IncidentInput, IncidentData),
    "get_service_health": (ServiceInput, HealthData),
    "get_service_metrics": (PageInput, MetricPage),
    "search_service_logs": (LogSearchInput, LogPage),
    "list_recent_deployments": (PageInput, DeploymentPage),
    "get_dependency_status": (ServiceInput, DependencyData),
}
ACTION_TOOLS = {
    "restart_simulated_worker": (ActionInput, ActionData),
    "rollback_simulated_configuration": (ActionInput, ActionData),
    "reset_simulated_dependency": (ActionInput, ActionData),
}
SUPERVISION_TOOLS = {
    "get_action_execution": (DurableInput, ExecutionStatus),
    "verify_simulated_remediation": (DurableInput, VerificationResult),
}
WRITE_TOOLS = frozenset(ACTION_TOOLS) | {"verify_simulated_remediation"}
TOOLS = READ_TOOLS | ACTION_TOOLS | SUPERVISION_TOOLS


def validate_arguments(name: str, arguments: dict) -> BaseModel:
    if name not in TOOLS:
        raise GatewayError(ErrorCode.UNKNOWN_TOOL)
    try:
        raw = json.dumps(arguments, allow_nan=False).encode()
        if len(raw) > MAX_ARGUMENT_BYTES:
            raise ValueError("oversized")
        return TOOLS[name][0].model_validate_json(raw)
    except (ValueError, TypeError, RecursionError):
        raise GatewayError(ErrorCode.INVALID_ARGUMENTS) from None


def failure(code: ErrorCode, request_id: str) -> dict:
    return ToolResponse[dict](
        ok=False,
        request_id=request_id,
        error=ErrorDetail(
            code=code,
            message=code.value.replace("_", " ").capitalize(),
            retryable=code
            in {ErrorCode.TIMEOUT, ErrorCode.DOWNSTREAM_UNAVAILABLE, ErrorCode.RATE_LIMITED},
        ),
    ).model_dump(mode="json")
