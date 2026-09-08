from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from project_g.infrastructure.database.repositories.recent_news_context import (
    SessionFactoryRecentNewsContextRepository,
)
from project_g.infrastructure.database.session import (
    SessionFactory,
)

_NOW = datetime(
    2026,
    9,
    6,
    9,
    30,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")


class FakeResult:
    def all(self) -> list[object]:
        return []


class FakeSession:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
    ) -> None:
        self.entered = False
        self.exited = False
        self.execute_called = False
        self.execute_error = execute_error

    def __enter__(self) -> "FakeSession":
        self.entered = True
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        self.exited = True

    def execute(
        self,
        _statement: Any,
    ) -> FakeResult:
        assert self.entered is True
        assert self.exited is False

        self.execute_called = True

        if self.execute_error is not None:
            raise self.execute_error

        return FakeResult()


def _factory(
    fake_session: FakeSession,
) -> SessionFactory:
    def factory() -> Session:
        return cast(Session, fake_session)

    return factory


def test_repository_closes_session_after_read() -> None:
    fake_session = FakeSession()

    repository = SessionFactoryRecentNewsContextRepository(
        session_factory=_factory(fake_session),
    )

    items = repository.list_recent_context(
        exclude_intake_id=_INTAKE_ID,
        published_since=_NOW - timedelta(days=14),
        published_until=_NOW,
        limit=50,
    )

    assert items == []
    assert fake_session.entered is True
    assert fake_session.execute_called is True
    assert fake_session.exited is True


def test_repository_closes_session_when_read_fails() -> None:
    fake_session = FakeSession(
        execute_error=RuntimeError("database failed"),
    )

    repository = SessionFactoryRecentNewsContextRepository(
        session_factory=_factory(fake_session),
    )

    with pytest.raises(
        RuntimeError,
        match="database failed",
    ):
        repository.list_recent_context(
            exclude_intake_id=_INTAKE_ID,
            published_since=_NOW - timedelta(days=14),
            published_until=_NOW,
            limit=50,
        )

    assert fake_session.entered is True
    assert fake_session.execute_called is True
    assert fake_session.exited is True
