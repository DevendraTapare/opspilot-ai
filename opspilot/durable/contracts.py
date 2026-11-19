from pydantic import BaseModel, ConfigDict, Field

from opspilot.schemas import ServiceName


class VerificationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(default=12, ge=1, le=30)
    arrival_interval_ms: int = Field(default=25, ge=0, le=100)
    max_error_rate: float = Field(default=0.05, ge=0, le=0.1)
    max_p95_latency_ms: float = Field(default=250, ge=1, le=299)


class ExecutionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class HumanOperator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject: str = Field(pattern=r"^[a-z][a-z0-9-]{2,39}$")
    os_user: str = Field(min_length=1, max_length=120)
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    services: frozenset[ServiceName]
    actions: frozenset[str]
