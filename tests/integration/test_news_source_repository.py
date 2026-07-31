from collections.abc import Iterator

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
from project_g.infrastructure.database.repositories import (
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    NewsSourceAlreadyExistsError,
    StoredNewsSourceNotFoundError,
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


def _source(
    source_id: str,
    *,
    official: bool = True,
    priority: int = 100,
    status: SourceStatus = SourceStatus.ENABLED,
) -> NewsSource:
    return NewsSource(
        source_id=source_id,
        name=source_id.replace("_", " ").title(),
        source_type=SourceType.WEBSITE,
        base_url=f"https://example.com/{source_id}",
        is_official=official,
        status=status,
        priority=priority,
    )


def test_repository_adds_and_retrieves_source(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)
    source = _source("giants_official")

    stored = repository.add(source)
    migrated_session.commit()

    loaded = repository.get_by_source_id(source.source_id)

    assert stored == source
    assert loaded == source


def test_repository_rejects_duplicate_source_id(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)
    source = _source("giants_official")

    repository.add(source)

    with pytest.raises(NewsSourceAlreadyExistsError):
        repository.add(source)


def test_repository_lists_all_sources_by_id(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)
    first = _source("giants_official")
    second = _source(
        "sports_news",
        official=False,
        priority=70,
    )

    repository.add(second)
    repository.add(first)

    assert repository.list_all() == (
        first,
        second,
    )


def test_repository_lists_collectable_sources_in_priority_order(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)
    official = _source(
        "giants_official",
        official=True,
        priority=80,
    )
    unofficial = _source(
        "sports_news",
        official=False,
        priority=100,
    )
    disabled = _source(
        "disabled_source",
        official=True,
        priority=100,
        status=SourceStatus.DISABLED,
    )

    repository.add(unofficial)
    repository.add(disabled)
    repository.add(official)

    assert repository.list_collectable() == (
        official,
        unofficial,
    )


def test_repository_updates_source_status(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)
    source = _source("giants_official")

    repository.add(source)

    updated = repository.update_status(
        source.source_id,
        SourceStatus.PAUSED,
    )
    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_source_id(source.source_id)

    assert updated.status is SourceStatus.PAUSED
    assert loaded is not None
    assert loaded.status is SourceStatus.PAUSED


def test_repository_rejects_status_update_for_missing_source(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)

    with pytest.raises(StoredNewsSourceNotFoundError):
        repository.update_status(
            "missing_source",
            SourceStatus.DISABLED,
        )
