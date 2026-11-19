"""Bounded graph state and provider output contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opspilot.schemas import ServiceName

ReadTool = Literal[
    "list_incidents",
    "get_incident",
    "get_service_health",
    "get_service_metrics",
    "search_service_logs",
    "list_recent_deployments",
    "get_dependency_status",
]
Action = Literal[
    "restart_simulated_worker",
    "rollback_simulated_configuration",
    "reset_simulated_dependency",
    "manual_investigation",
]

EvidenceReference = Annotated[
    str,
    Field(
        pattern=r"^e[0-9]{3}$",
        max_length=4,
        description="One existing observation ID, such as e002; no prose or unobserved facts.",
    ),
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1000)


class RunRequest(Contract):
    incident_id: UUID
    service_name: ServiceName
    goal: str = Field(
        default="Investigate this incident and recommend a supported next action.",
        min_length=1,
        max_length=500,
    )
    max_tool_calls: int = Field(default=8, ge=1, le=12)
    max_model_calls: int = Field(default=14, ge=1, le=24)
    max_seconds: float = Field(default=180, ge=0.1, le=600)
    call_timeout_seconds: float = Field(default=30, ge=0.05, le=60)
    max_investigation_rounds: int = Field(default=4, ge=1, le=10)
    max_estimated_tokens: int = Field(default=160000, ge=1, le=1000000)
    max_prompt_estimated_tokens: int = Field(default=32000, ge=1, le=65000)


class DiagnosticStep(Contract):
    tool_name: ReadTool
    service_name: ServiceName
    incident_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=10)
    query: str = Field(default="", max_length=128)
    rationale: str = Field(min_length=1, max_length=500)


class ModelToolCall(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    name: Literal["select_diagnostic_tool"] = "select_diagnostic_tool"
    arguments: DiagnosticStep


class Triage(Contract):
    summary: str = Field(min_length=1, max_length=500)
    alternatives: list[str] = Field(min_length=2, max_length=4)


class Hypothesis(Contract):
    id: str = Field(pattern=r"^h[1-9][0-9]?$", max_length=3)
    description: str = Field(min_length=1, max_length=500)
    supporting_evidence: list[EvidenceReference] = Field(max_length=8)
    contradicting_evidence: list[EvidenceReference] = Field(max_length=8)


class Assessment(Contract):
    hypotheses: list[Hypothesis] = Field(min_length=2, max_length=4)
    decision: Literal["investigate", "propose", "abstain"]
    justification: str = Field(min_length=1, max_length=700)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    uncertainty: list[str] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_hypotheses(self):
        if len({h.id for h in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("hypothesis IDs must be unique")
        return self


class RootCause(Contract):
    hypothesis_id: str = Field(pattern=r"^h[1-9][0-9]?$", max_length=3)
    service_name: ServiceName
    explanation: str = Field(min_length=1, max_length=800)
    evidence_refs: list[EvidenceReference] = Field(min_length=2, max_length=8)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    uncertainty: list[str] = Field(min_length=1, max_length=5)


class Remediation(Contract):
    action: Action
    service_name: ServiceName
    rationale: str = Field(min_length=1, max_length=700)
    evidence_refs: list[EvidenceReference] = Field(min_length=2, max_length=8)
    risks: list[str] = Field(min_length=1, max_length=4)
    verification_steps: list[str] = Field(min_length=1, max_length=5)
    human_approval_required: Literal[True] = True


class Observation(Contract):
    id: str
    tool_name: ReadTool
    service_name: ServiceName
    request_id: str
    data: dict
    untrusted_data: Literal[True] = True


class ToolCall(Contract):
    tool_name: ReadTool
    arguments: dict
    outcome: str
    evidence_ref: str | None = None
    latency_ms: float
    request_id: str | None = None
    model_call: ModelToolCall | None = None


class ErrorInfo(Contract):
    node: str
    code: str
    # Fixed safe messages only; never provider response bodies or exception strings.
    message: str


class Usage(Contract):
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usage_complete: bool = True
    estimated_cost_usd: float | None = None
    estimated_input_tokens: int = 0
    estimated_token_reservation: int = 0


Status = Literal["running", "completed", "abstained", "budget_exhausted", "failed"]


class Recommendation(Contract):
    status: Status
    summary: str
    root_cause: RootCause | None
    proposed_remediation: Remediation | None
    evidence_refs: list[str]
    uncertainty: list[str]
    automatic_action_executed: Literal[False] = False


class InvestigationState(Contract):
    request: RunRequest
    run_id: UUID
    mode: Literal["real", "fixture"]
    provider: str
    model: str
    incident_id: UUID
    goal: str
    observations: list[Observation] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    tool_call_history: list[ToolCall] = Field(default_factory=list)
    current_hypotheses: list[Hypothesis] = Field(default_factory=list)
    proposed_next_diagnostic_step: DiagnosticStep | None = None
    proposed_model_call: ModelToolCall | None = None
    candidate_root_cause: RootCause | None = None
    proposed_remediation: Remediation | None = None
    confidence: float = 0
    uncertainty: list[str] = Field(default_factory=lambda: ["Evidence has not been assessed."])
    run_status: Status = "running"
    errors: list[ErrorInfo] = Field(default_factory=list)
    transitions: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    assessment: Assessment | None = None
    triage: Triage | None = None
    recommendation: Recommendation | None = None
    latency_ms: float = 0
