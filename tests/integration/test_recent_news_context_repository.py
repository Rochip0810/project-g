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
from project_g.domain.news.article_metadata import NewsArticleMetadata
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.infrastructure.database.repositories.manual_news_intakes import (
    SqlAlchemyManualNewsIntakeRepository,
)
from project_g.infrastructure.database.repositories.news_article_metadata import (
    SqlAlchemyNewsArticleMetadataRepository,
)
from project_g.infrastructure.database.repositories.news_sources import (
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.database.repositories.recent_news_context import (
    SqlAlchemyRecentNewsContextRepository,
)

_NOW = datetime(
    2026,
    8,
    29,
    9,
    0,
    tzinfo=UTC,
)
_CREATED_AT = _NOW - timedelta(days=20)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(
        alembic_config,
        "head",
    )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def _source() -> NewsSource:
    return NewsSource(
        source_id="hochi_giants_articles",
        name="Sports Hochi Giants",
        source_type=SourceType.WEBSITE,
        base_url="https://hochi.news/",
        is_official=False,
        status=SourceStatus.ENABLED,
        priority=92,
    )


def _seed_item(
    session: Session,
    *,
    number: int,
    published_at: datetime | None,
    metadata_state: str = "manual",
) -> UUID:
    intake_id = UUID(f"00000000-0000-0000-0000-{number:012d}")
    metadata_id = UUID(f"10000000-0000-0000-0000-{number:012d}")

    intake = ManualNewsIntake(
        intake_id=intake_id,
        source_id="hochi_giants_articles",
        submitted_url=f"https://hochi.news/articles/{number}",
        canonical_url=f"https://hochi.news/articles/{number}",
        submitted_at=_CREATED_AT,
    )

    SqlAlchemyManualNewsIntakeRepository(session).add(intake)

    repository = SqlAlchemyNewsArticleMetadataRepository(session)

    pending = NewsArticleMetadata.pending(
        metadata_id=metadata_id,
        intake_id=intake_id,
        created_at=_CREATED_AT,
    )
    repository.add(pending)

    if metadata_state == "manual":
        repository.update(
            pending.record_manual(
                title=f"Giants recent context test {number}",
                published_at=published_at,
                description=f"Background description {number}.",
                updated_at=_UPDATED_AT,
            )
        )
    elif metadata_state == "failed":
        repository.update(
            pending.mark_failed(
                reason="Context test failure.",
                updated_at=_UPDATED_AT,
            )
        )
    elif metadata_state != "pending":
        raise ValueError(f"Unknown metadata_state: {metadata_state}")

    return intake_id


def test_repository_returns_recent_usable_context_in_newest_first_order(
    migrated_session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(migrated_session).add(_source())

    target_id = _seed_item(
        migrated_session,
        number=1,
        published_at=_NOW - timedelta(hours=1),
    )

    newest_id = _seed_item(
        migrated_session,
        number=2,
        published_at=_NOW - timedelta(hours=2),
    )

    older_id = _seed_item(
        migrated_session,
        number=3,
        published_at=_NOW - timedelta(days=5),
    )

    _seed_item(
        migrated_session,
        number=4,
        published_at=_NOW - timedelta(days=15),
    )

    _seed_item(
        migrated_session,
        number=5,
        published_at=None,
        metadata_state="pending",
    )

    _seed_item(
        migrated_session,
        number=6,
        published_at=None,
        metadata_state="failed",
    )

    _seed_item(
        migrated_session,
        number=7,
        published_at=_NOW + timedelta(hours=1),
    )

    migrated_session.commit()

    repository = SqlAlchemyRecentNewsContextRepository(migrated_session)

    items = repository.list_recent_context(
        exclude_intake_id=target_id,
        published_since=_NOW - timedelta(days=14),
        published_until=_NOW,
        limit=50,
    )

    assert [item.intake_id for item in items] == [
        newest_id,
        older_id,
    ]

    assert items[0].source_id == "hochi_giants_articles"
    assert items[0].canonical_url == "https://hochi.news/articles/2"
    assert items[0].title == "Giants recent context test 2"
    assert items[0].description == "Background description 2."
    assert items[0].published_at == _NOW - timedelta(hours=2)

    limited_items = repository.list_recent_context(
        exclude_intake_id=target_id,
        published_since=_NOW - timedelta(days=14),
        published_until=_NOW,
        limit=1,
    )

    assert [item.intake_id for item in limited_items] == [
        newest_id,
    ]


def test_repository_rejects_naive_published_since(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyRecentNewsContextRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="published_since must be timezone-aware",
    ):
        repository.list_recent_context(
            exclude_intake_id=UUID("00000000-0000-0000-0000-000000000001"),
            published_since=datetime(2026, 8, 29, 9, 0),
            published_until=_NOW,
        )


@pytest.mark.parametrize(
    "limit",
    [
        0,
        101,
    ],
)
def test_repository_rejects_invalid_limit(
    migrated_session: Session,
    limit: int,
) -> None:
    repository = SqlAlchemyRecentNewsContextRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        repository.list_recent_context(
            exclude_intake_id=UUID("00000000-0000-0000-0000-000000000001"),
            published_since=_NOW - timedelta(days=14),
            published_until=_NOW,
            limit=limit,
        )


def test_repository_rejects_naive_published_until(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyRecentNewsContextRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="published_until must be timezone-aware",
    ):
        repository.list_recent_context(
            exclude_intake_id=UUID("00000000-0000-0000-0000-000000000001"),
            published_since=_NOW - timedelta(days=14),
            published_until=datetime(2026, 8, 29, 9, 0),
        )


def test_repository_rejects_reversed_time_window(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyRecentNewsContextRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="published_until must not be earlier than published_since",
    ):
        repository.list_recent_context(
            exclude_intake_id=UUID("00000000-0000-0000-0000-000000000001"),
            published_since=_NOW,
            published_until=_NOW - timedelta(days=1),
        )
