from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from graduation_exception_agent.config import AppSettings, ExecutionMode, load_settings


CONFIG_KEYS = {
    "EXECUTION_MODE",
    "LOG_LEVEL",
    "SIMULATION_SEED",
    "AWS_PROFILE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "BEDROCK_MODEL_ID",
    "BEDROCK_TEMPERATURE",
    "BEDROCK_MAX_TOKENS",
    "API_HOST",
    "API_PORT",
    "FRONTEND_ORIGIN",
    "DATA_DIR",
    "CHECKPOINT_DB",
}


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_load_from_isolated_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "\n".join(
            [
                "EXECUTION_MODE=bedrock",
                "AWS_ACCESS_KEY_ID=test-access-key",
                "AWS_SECRET_ACCESS_KEY=test-secret-value",
                "AWS_REGION=ap-southeast-1",
                "BEDROCK_MODEL_ID=test.model-v1",
                "BEDROCK_TEMPERATURE=0.2",
                "BEDROCK_MAX_TOKENS=1024",
                "API_PORT=9000",
                "FRONTEND_ORIGIN=http://localhost:3000",
                "DATA_DIR=fixtures/data",
                "CHECKPOINT_DB=fixtures/checkpoints.sqlite3",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.execution_mode is ExecutionMode.BEDROCK
    assert settings.api_port == 9000
    assert settings.data_dir == Path("fixtures/data")
    assert settings.aws_secret_access_key is not None
    assert settings.aws_secret_access_key.get_secret_value() == "test-secret-value"
    assert "test-secret-value" not in repr(settings)


def test_importable_defaults_need_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    settings = load_settings(None)
    assert settings.execution_mode is ExecutionMode.SIMULATION
    assert settings.aws_access_key_id is None
    assert settings.aws_secret_access_key is None


def test_fixture_execution_mode_is_supported() -> None:
    settings = AppSettings(_env_file=None, EXECUTION_MODE="fixture")
    assert settings.execution_mode is ExecutionMode.FIXTURE


def test_incomplete_static_credential_pair_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be supplied together"):
        AppSettings(
            _env_file=None,
            AWS_ACCESS_KEY_ID="access-only",
        )


def test_bedrock_mode_requires_model_id() -> None:
    with pytest.raises(ValidationError, match="BEDROCK_MODEL_ID"):
        AppSettings(
            _env_file=None,
            EXECUTION_MODE="bedrock",
            BEDROCK_MODEL_ID=None,
        )


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, API_PORT=70000)
