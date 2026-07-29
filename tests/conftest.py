import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config as AlembicConfig
from fakeredis import FakeStrictRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from project_g.infrastructure.config import AppEnvironment, Settings
from project_g.infrastructure.database import create_alembic_config
from project_g.interfaces.api import create_app
from project_g.monitoring import ReadinessReport


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-docker",
        action="store_true",
        default=False,
        help="Run local Docker Compose smoke tests.",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    run_docker = bool(config.getoption("--run-docker"))
    skip_docker = pytest.mark.skip(
        reason="Docker tests require --run-docker",
    )

    for item in items:
        normalized_path = item.path.as_posix()

        if "/tests/docker/" in normalized_path:
            item.add_marker(pytest.mark.docker)

            if not run_docker:
                item.add_marker(skip_docker)

        elif "/tests/integration/" in normalized_path:
            item.add_marker(pytest.mark.integration)

        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def test_settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": AppEnvironment.TEST,
            "app_name": "project-g-test",
            "app_version": "0.1.0-test",
            "log_level": "WARNING",
            "database_host": "db-test",
            "database_name": "project_g_test",
            "database_user": "project_g_test",
            "redis_host": "queue-test",
            "publishing_enabled": False,
        }
    )


@pytest.fixture
def readiness_report() -> ReadinessReport:
    return ReadinessReport(
        database=True,
        redis=True,
        migrations=True,
    )


@pytest.fixture
def api_app(
    test_settings: Settings,
    readiness_report: ReadinessReport,
) -> FastAPI:
    return create_app(
        test_settings,
        readiness_probe=lambda: readiness_report,
    )


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def fake_redis() -> Iterator[Any]:
    client = FakeStrictRedis(decode_responses=False)

    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def sqlite_database_url(tmp_path: Path) -> str:
    database_path = tmp_path / "project-g-test.db"

    return f"sqlite+pysqlite:///{database_path.as_posix()}"


@pytest.fixture
def database_engine(
    sqlite_database_url: str,
) -> Iterator[Engine]:
    engine = create_engine(sqlite_database_url)

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def alembic_config(
    sqlite_database_url: str,
) -> AlembicConfig:
    return create_alembic_config(sqlite_database_url)


@pytest.fixture
def docker_base_url() -> str:
    return os.getenv(
        "PROJECT_G_DOCKER_BASE_URL",
        "http://127.0.0.1:8000",
    ).rstrip("/")
