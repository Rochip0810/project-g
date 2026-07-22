from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_name: str = "project-g"
    app_version: str = "0.1.0"
    app_secret_key: SecretStr = SecretStr("")
    log_level: str = "INFO"
    timezone: str = "Asia/Tokyo"

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)

    database_host: str = "db"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "project_g"
    database_user: str = "project_g"
    database_password: SecretStr = SecretStr("")

    redis_host: str = "queue"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_database: int = Field(default=0, ge=0)

    rq_default_queue: str = "default"
    rq_job_timeout_seconds: int = Field(default=300, ge=1)
    rq_max_retries: int = Field(default=3, ge=0)

    publishing_enabled: bool = False

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env is not AppEnvironment.PRODUCTION:
            return self

        missing: list[str] = []

        if not self.app_secret_key.get_secret_value():
            missing.append("APP_SECRET_KEY")

        if not self.database_password.get_secret_value():
            missing.append("DATABASE_PASSWORD")

        if missing:
            missing_values = ", ".join(missing)
            raise ValueError(f"Production settings require non-empty values for: {missing_values}")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
