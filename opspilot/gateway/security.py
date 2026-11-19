import hashlib
import hmac
import json
import threading
import time
from collections import defaultdict, deque
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from opspilot.gateway.contracts import TOOLS, ErrorCode, GatewayError
from opspilot.schemas import ServiceName


class Caller(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{2,39}$")]
    token_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    services: frozenset[ServiceName]
    tools: frozenset[str]

    @field_validator("tools")
    @classmethod
    def known_permissions(cls, value):
        if not value or not value.issubset(TOOLS):
            raise ValueError("permissions must use the strict tool allowlist")
        return value


class GatewaySettings(BaseSettings):
    # Never load a general .env into the unprivileged MCP process.
    model_config = SettingsConfigDict(env_prefix="OPSPILOT_GATEWAY_", extra="ignore")
    callers: SecretStr
    delegation_key: SecretStr = Field(min_length=32)
    backend_url: str = "http://authorizer:8000"
    timeout_seconds: float = Field(default=3, ge=0.1, le=10)
    requests_per_minute: int = Field(default=60, ge=1, le=600)
    actions_per_minute: int = Field(default=5, ge=1, le=60)

    @field_validator("backend_url")
    @classmethod
    def local_backend(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"authorizer", "127.0.0.1", "localhost"}
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("backend must be the explicitly configured local simulator authorizer")
        return value.rstrip("/")

    def policies(self) -> dict[str, Caller]:
        values = json.loads(self.callers.get_secret_value())
        if not isinstance(values, list) or not 1 <= len(values) <= 16:
            raise ValueError("configure 1 to 16 local callers")
        callers = [Caller.model_validate(value) for value in values]
        if len({c.subject for c in callers}) != len(callers):
            raise ValueError("duplicate caller identity")
        if len({c.token_sha256 for c in callers}) != len(callers):
            raise ValueError("duplicate caller credential")
        return {caller.subject: caller for caller in callers}


class AuthorizerSettings(GatewaySettings):
    database_url: SecretStr
    approval_key: SecretStr = Field(min_length=32)
    actions_enabled: bool = False


def authenticate(header: str, policies: dict[str, Caller]) -> Caller | None:
    if not header.startswith("Bearer ") or len(header) > 256:
        return None
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    for caller in policies.values():
        if hmac.compare_digest(caller.token_sha256, digest):
            return caller
    return None


def check_scope(caller: Caller, name: str, service: str) -> None:
    if name not in caller.tools or service not in caller.services:
        raise GatewayError(ErrorCode.FORBIDDEN)


class RateLimiter:
    """Bounded cardinality: keys are configured caller IDs, never caller-supplied IDs."""

    def __init__(self):
        self.windows = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, maximum: int) -> bool:
        with self.lock:
            now = time.monotonic()
            window = self.windows[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= maximum:
                return False
            window.append(now)
            return True


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def signature(
    key: SecretStr, subject: str, path: str, request_id: str, timestamp: str, body: bytes
) -> str:
    message = "\n".join((subject, path, request_id, timestamp, hashlib.sha256(body).hexdigest()))
    return hmac.new(key.get_secret_value().encode(), message.encode(), hashlib.sha256).hexdigest()


def delegated_headers(
    settings: GatewaySettings, subject: str, path: str, request_id: str, body: bytes
) -> dict:
    timestamp = str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "X-OpsPilot-Caller": subject,
        "X-OpsPilot-Request-ID": request_id,
        "X-OpsPilot-Time": timestamp,
        "X-OpsPilot-Signature": signature(
            settings.delegation_key, subject, path, request_id, timestamp, body
        ),
    }


def verify_delegation(
    settings: GatewaySettings, headers, path: str, body: bytes
) -> tuple[str, str]:
    try:
        subject = headers["x-opspilot-caller"]
        request_id = str(UUID(headers["x-opspilot-request-id"]))
        timestamp = headers["x-opspilot-time"]
        if abs(time.time() - int(timestamp)) > 30:
            raise ValueError("expired")
        expected = signature(settings.delegation_key, subject, path, request_id, timestamp, body)
        if not hmac.compare_digest(expected, headers["x-opspilot-signature"]):
            raise ValueError("signature")
        return subject, request_id
    except (KeyError, ValueError, TypeError):
        raise GatewayError(ErrorCode.FORBIDDEN) from None
