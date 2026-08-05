from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    NewsArticleMetadataAlreadyExistsError,
    NewsArticleMetadataNotFoundError,
)

_METADATA_1_ID = UUID("6afddf73-9884-4553-a6b4-fc7ad593713d")
_METADATA_2_ID = UUID("39a4fcc5-65e3-4ca1-a3d8-d218050b766c")
_INTAKE_ID = UUID("3e697abe-ab72-42e0-ae0d-d9a95da60220")
_CREATED_AT = datetime(
    2026,
    8,
    5,
    15,
    0,
    tzinfo=UTC,
)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)
_PUBLISHED_AT = datetime(
    2026,
    8,
    5,
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


def _intake() -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/555555/"),
        canonical_url=("https://www.giants.jp/news/555555/"),
        submitted_at=_CREATED_AT,
    )


def _pending(
    metadata_id: UUID = _METADATA_1_ID,
) -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=metadata_id,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _seed_source_and_intake(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())
    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())


def test_repository_adds_and_retrieves_metadata(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)
    repository = SqlAlchemyNewsArticleMetadataRepository(migrated_session)
    metadata = _pending()

    stored = repository.add(metadata)
    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == metadata
    assert repository.get_by_metadata_id(metadata.metadata_id) == metadata
    assert repository.get_by_intake_id(metadata.intake_id) == metadata


def test_repository_updates_manual_metadata(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)
    repository = SqlAlchemyNewsArticleMetadataRepository(migrated_session)
    pending = _pending()
    repository.add(pending)

    manual = pending.record_manual(
        title="Giants announce roster update",
        published_at=_PUBLISHED_AT,
        description="Official team announcement.",
        updated_at=_UPDATED_AT,
    )

    stored = repository.update(manual)
    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_metadata_id(manual.metadata_id)

    assert stored.status is NewsMetadataStatus.MANUAL
    assert stored.title == "Giants announce roster update"
    assert loaded == manual


def test_repository_rejects_duplicate_intake_metadata(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)
    repository = SqlAlchemyNewsArticleMetadataRepository(migrated_session)

    repository.add(_pending())

    with pytest.raises(NewsArticleMetadataAlreadyExistsError):
        repository.add(_pending(metadata_id=_METADATA_2_ID))


def test_repository_update_rejects_unknown_metadata(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)
    repository = SqlAlchemyNewsArticleMetadataRepository(migrated_session)

    with pytest.raises(NewsArticleMetadataNotFoundError):
        repository.update(_pending())
