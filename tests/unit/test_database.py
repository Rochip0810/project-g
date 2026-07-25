from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    Base,
    SessionFactory,
    build_database_url,
    check_database_connection,
    create_database_engine,
    create_session_factory,
    session_scope,
)


def _create_database_settings() -> Settings:
    return Settings(
        database_host="postgres.example",
        database_port=5432,
        database_name="project_g_test",
        database_user="project_g_user",
        database_password=SecretStr("p@ss/word"),
    )


def test_declarative_base_has_metadata() -> None:
    assert Base.metadata is not None


def test_database_url_uses_psycopg_and_hides_password() -> None:
    url = build_database_url(_create_database_settings())

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "project_g_user"
    assert url.password == "p@ss/word"
    assert url.host == "postgres.example"
    assert url.port == 5432
    assert url.database == "project_g_test"

    rendered_url = str(url)

    assert "p@ss/word" not in rendered_url
    assert "***" in rendered_url


def test_database_engine_can_be_created_without_connecting() -> None:
    engine = create_database_engine(_create_database_settings())

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool._pre_ping is True
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


def test_session_factory_creates_configured_session() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        assert isinstance(session, Session)
        assert session.autoflush is False
        assert session.expire_on_commit is False
    finally:
        session.close()
        engine.dispose()


def test_session_scope_commits_and_closes_on_success() -> None:
    session_mock = MagicMock(spec=Session)
    factory_mock = MagicMock(return_value=session_mock)
    session_factory = cast(SessionFactory, factory_mock)

    with session_scope(session_factory) as session:
        assert session is session_mock

    session_mock.commit.assert_called_once_with()
    session_mock.rollback.assert_not_called()
    session_mock.close.assert_called_once_with()


def test_session_scope_rolls_back_and_closes_on_failure() -> None:
    session_mock = MagicMock(spec=Session)
    factory_mock = MagicMock(return_value=session_mock)
    session_factory = cast(SessionFactory, factory_mock)

    with (
        pytest.raises(RuntimeError, match="transaction failed"),
        session_scope(session_factory),
    ):
        raise RuntimeError("transaction failed")

    session_mock.commit.assert_not_called()
    session_mock.rollback.assert_called_once_with()
    session_mock.close.assert_called_once_with()


def test_database_health_check_executes_select_one() -> None:
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = 1

    connection_mock = MagicMock()
    connection_mock.execute.return_value = result_mock

    engine_mock = MagicMock(spec=Engine)
    engine_mock.connect.return_value.__enter__.return_value = connection_mock
    engine_mock.connect.return_value.__exit__.return_value = False

    result = check_database_connection(cast(Engine, engine_mock))

    assert result is True

    statement = connection_mock.execute.call_args.args[0]
    assert str(statement) == "SELECT 1"


def test_database_health_check_returns_false_on_connection_error() -> None:
    engine_mock = MagicMock(spec=Engine)
    engine_mock.connect.side_effect = SQLAlchemyError("database unavailable")

    result = check_database_connection(cast(Engine, engine_mock))

    assert result is False
