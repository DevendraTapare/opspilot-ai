from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_DASHBOARD_", env_file=".dashboard.env", extra="ignore"
    )
    service_key: SecretStr
    reader_token: SecretStr
    api_url: str = "http://127.0.0.1:8084"
    control_token: SecretStr
    origin: str = "http://127.0.0.1:3000"
    actions_enabled: bool = False

    @field_validator("api_url", "origin")
    @classmethod
    def local_url(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("dashboard URLs must be explicit loopback HTTP origins")
        return value.rstrip("/")
