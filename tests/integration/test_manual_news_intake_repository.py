from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    ManualNewsIntakeAlreadyExistsError,
)

_FIRST_ID = UUID("5525ddbf-20bd-424c-a573-91fd187f9218")
_SECOND_ID = UUID("383c5256-effe-4e57-a115-1249c7fe7e1e")
_SUBMITTED_AT = datetime(
    2026,
    8,
    3,
    12,
    0,
    tzinfo=UTC,
)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def _source() -> NewsSource:
    return NewsSource(
        source_id="giants_official_news",
        name="Giants Official News",
        source_type=SourceType.WEBSITE,
        base_url="https://www.giants.jp/news/",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=100,
    )


def _intake(
    *,
    intake_id: UUID = _FIRST_ID,
    submitted_url: str = ("https://www.giants.jp/news/12345/"),
    canonical_url: str = ("https://www.giants.jp/news/12345/"),
) -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=intake_id,
        source_id="giants_official_news",
        submitted_url=submitted_url,
        canonical_url=canonical_url,
        submitted_at=_SUBMITTED_AT,
    )


def _seed_source(
    session: Session,
) -> None:
    source_repository = SqlAlchemyNewsSourceRepository(session)
    source_repository.add(_source())


def test_repository_adds_and_retrieves_intake(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)
    intake = _intake()

    stored = repository.add(intake)
    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_canonical_url(intake.canonical_url)

    assert stored == intake
    assert loaded == intake


def test_repository_detects_existing_url(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)
    intake = _intake()

    assert repository.exists_by_canonical_url(intake.canonical_url) is False

    repository.add(intake)

    assert repository.exists_by_canonical_url(intake.canonical_url) is True


def test_repository_returns_none_for_unknown_url(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)

    assert repository.get_by_canonical_url("https://www.giants.jp/news/missing/") is None


def test_repository_rejects_duplicate_canonical_url(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)

    repository.add(_intake())

    duplicate = _intake(
        intake_id=_SECOND_ID,
        submitted_url=("https://www.giants.jp/news/12345/?utm_source=google"),
    )

    with pytest.raises(ManualNewsIntakeAlreadyExistsError):
        repository.add(duplicate)

    assert repository.get_by_canonical_url(duplicate.canonical_url) is not None
