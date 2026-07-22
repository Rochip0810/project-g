import pytest
from pydantic import SecretStr, ValidationError

from project_g.infrastructure.config import AppEnvironment, Settings


def test_development_settings_load_with_safe_defaults() -> None:
    settings = Settings(app_env=AppEnvironment.DEVELOPMENT)

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.app_name == "project-g"
    assert settings.publishing_enabled is False


def test_test_environment_loads_from_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PUBLISHING_ENABLED", "false")

    settings = Settings()

    assert settings.app_env is AppEnvironment.TEST
    assert settings.publishing_enabled is False


def test_invalid_environment_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"app_env": "invalid-environment"})


def test_production_requires_secret_values() -> None:
    with pytest.raises(
        ValidationError,
        match="Production settings require non-empty values",
    ):
        Settings(app_env=AppEnvironment.PRODUCTION)


def test_production_loads_when_required_secrets_exist() -> None:
    settings = Settings(
        app_env=AppEnvironment.PRODUCTION,
        app_secret_key=SecretStr("test-application-secret"),
        database_password=SecretStr("test-database-password"),
    )

    assert settings.app_env is AppEnvironment.PRODUCTION
    assert settings.publishing_enabled is False


def test_invalid_api_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"api_port": 70000})
