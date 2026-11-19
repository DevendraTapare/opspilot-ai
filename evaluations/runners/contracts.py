"""Versioned controller contracts; public inputs are separate from private answers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opspilot.agent.schemas import DiagnosticStep
from opspilot.schemas import FaultCreate, ServiceName

Mechanism = Literal[
    "worker_capacity",
    "processing_latency",
    "configuration",
    "dependency_unavailable",
    "database_pool",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicCase(Strict):
    incident_id: str = Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    service_name: ServiceName
    goal: str = "Investigate this incident using operational evidence; abstain if inconclusive."
    max_tool_calls: int = Field(default=8, ge=1, le=12)
    max_model_calls: int = Field(default=14, ge=1, le=24)
    max_seconds: float = Field(default=180, ge=0.1, le=600)
    call_timeout_seconds: float = Field(default=15, ge=0.05, le=60)


class Case(Strict):
    id: str = Field(pattern=r"^op5-[0-9]{3}$")
    split: Literal["calibration", "development", "held_out"]
    family: str
    seed: int
    target: ServiceName
    faults: list[FaultCreate]
    count: int = Field(ge=1, le=50)
    interval_ms: int = Field(ge=0, le=100)
    history: bool = False
    missing: Literal["none", "metrics", "logs", "all"] = "none"
    contradict_logs: bool = False
    fail_tools: list[str] = Field(default_factory=list)
    operational_case: str | None = None
    answerable: bool
    expected_service: ServiceName | None
    expected_mechanism: Mechanism | None
    expected_resolution: Literal["diagnose", "abstain", "healthy"]
    required_tools: list[str]


class Choice(Strict):
    decision: Literal["investigate", "diagnose", "abstain"]
    step: DiagnosticStep | None
    service_name: ServiceName | None
    mechanism: Mechanism | None
    evidence_refs: list[str] = Field(max_length=8)
    explanation: str = Field(min_length=1, max_length=800)


class Prediction(Strict):
    status: Literal["diagnosed", "abstained", "timeout", "failed", "excluded"]
    service: ServiceName | None = None
    mechanism: Mechanism | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_supported: bool = False
    error_code: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_calls: int = 0


class Trial(Strict):
    trace_id: str | None = None
    case_id: str
    split: str
    family: str
    arm: str
    mode: Literal["rules", "real", "fixture"]
    prediction: Prediction
    elapsed_ms: float
    tool_calls: list[dict]
    correct_root: bool | None
    task_success: bool
    unsupported: bool
    appropriate_calls: int
    required_tool_coverage: bool
    unauthorized_action_attempts: int = 0
    approval_bypass_attempts: int = 0
    observed_side_effects: int = 0
    estimated_cost_usd: float | None = None
