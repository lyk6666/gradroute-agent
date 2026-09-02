"""Environment-driven application configuration.

Settings are never instantiated at import time. This keeps imports free of
credential requirements and lets tests pass an isolated environment file.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(StrEnum):
    """Supported backend execution modes."""

    SIMULATION = "simulation"
    FIXTURE = "fixture"
    BEDROCK = "bedrock"


class AppSettings(BaseSettings):
    """Validated configuration loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.SIMULATION,
        validation_alias="EXECUTION_MODE",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    simulation_seed: int = Field(default=20260830, validation_alias="SIMULATION_SEED")

    aws_profile: str | None = Field(default=None, validation_alias="AWS_PROFILE")
    aws_access_key_id: SecretStr | None = Field(
        default=None,
        validation_alias="AWS_ACCESS_KEY_ID",
    )
    aws_secret_access_key: SecretStr | None = Field(
        default=None,
        validation_alias="AWS_SECRET_ACCESS_KEY",
    )
    aws_session_token: SecretStr | None = Field(
        default=None,
        validation_alias="AWS_SESSION_TOKEN",
    )
    aws_region: str = Field(default="ap-southeast-1", validation_alias="AWS_REGION")

    bedrock_model_id: str | None = Field(
        default=None,
        validation_alias="BEDROCK_MODEL_ID",
    )
    bedrock_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        validation_alias="BEDROCK_TEMPERATURE",
    )
    bedrock_max_tokens: int = Field(
        default=2048,
        ge=1,
        validation_alias="BEDROCK_MAX_TOKENS",
    )
    ui_narration_enabled: bool = Field(
        default=True,
        validation_alias="UI_NARRATION_ENABLED",
    )

    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, ge=1, le=65535, validation_alias="API_PORT")
    frontend_origin: AnyHttpUrl = Field(
        default="http://localhost:3000",
        validation_alias="FRONTEND_ORIGIN",
    )
    data_dir: Path = Field(default=Path("data"), validation_alias="DATA_DIR")
    evaluation_dir: Path = Field(
        default=Path("evaluation"), validation_alias="EVALUATION_DIR"
    )
    checkpoint_db: Path = Field(
        default=Path("var/checkpoints.sqlite3"),
        validation_alias="CHECKPOINT_DB",
    )

    @model_validator(mode="after")
    def validate_static_credentials(self) -> AppSettings:
        """Reject incomplete static AWS credential pairs.

        A profile or ambient IAM credentials remain valid alternatives, so
        static credentials are not required even in Bedrock mode.
        """

        has_access_key = self.aws_access_key_id is not None
        has_secret_key = self.aws_secret_access_key is not None
        if has_access_key != has_secret_key:
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be supplied together"
            )
        if self.execution_mode is ExecutionMode.BEDROCK and not self.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required when EXECUTION_MODE=bedrock")
        return self


def load_settings(env_file: str | Path | None = ".env") -> AppSettings:
    """Load settings from an explicit file plus the process environment."""

    return AppSettings(_env_file=env_file)  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the process-wide settings instance on first explicit request."""

    return load_settings()
