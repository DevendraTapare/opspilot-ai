from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPSPILOT_", env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://opspilot:opspilot@127.0.0.1:55432/opspilot"
    )
    control_token: SecretStr
    log_level: str = "INFO"

    @field_validator("control_token")
    @classmethod
    def strong_control_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 32 or token in {"replace-with-a-random-token-of-at-least-32-characters"}:
            raise ValueError("control token must be a generated secret of at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
