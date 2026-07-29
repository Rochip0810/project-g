from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from project_g.infrastructure.config import (
    AppEnvironment,
    Settings,
)


def test_shared_settings_fixture(
    test_settings: Settings,
) -> None:
    assert test_settings.app_env is AppEnvironment.TEST
    assert test_settings.app_name == "project-g-test"
    assert test_settings.publishing_enabled is False


def test_shared_api_client_fixture(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/health/readiness")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_shared_fake_redis_fixture(
    fake_redis: Any,
) -> None:
    assert fake_redis.set("project-g:test", "ok") is True
    assert fake_redis.get("project-g:test") == b"ok"


def test_shared_database_engine_fixture(
    database_engine: Engine,
) -> None:
    with database_engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
