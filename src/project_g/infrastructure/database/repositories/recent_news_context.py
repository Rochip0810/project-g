from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from project_g.domain.news.article_metadata import NewsMetadataStatus
from project_g.domain.news.recent_context import RecentNewsContextItem
from project_g.infrastructure.database.models import (
    ManualNewsIntakeRecord,
    NewsArticleMetadataRecord,
)
from project_g.infrastructure.database.session import SessionFactory


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


class SqlAlchemyRecentNewsContextRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def list_recent_context(
        self,
        *,
        exclude_intake_id: UUID,
        published_since: datetime,
        published_until: datetime,
        limit: int = 50,
    ) -> list[RecentNewsContextItem]:
        if published_since.tzinfo is None or published_since.utcoffset() is None:
            raise ValueError("published_since must be timezone-aware")

        if published_until.tzinfo is None or published_until.utcoffset() is None:
            raise ValueError("published_until must be timezone-aware")

        if published_until < published_since:
            raise ValueError("published_until must not be earlier than published_since")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        statement = (
            select(
                NewsArticleMetadataRecord.intake_id,
                ManualNewsIntakeRecord.source_id,
                ManualNewsIntakeRecord.canonical_url,
                NewsArticleMetadataRecord.title,
                NewsArticleMetadataRecord.description,
                NewsArticleMetadataRecord.published_at,
            )
            .join(
                ManualNewsIntakeRecord,
                ManualNewsIntakeRecord.intake_id == NewsArticleMetadataRecord.intake_id,
            )
            .where(
                NewsArticleMetadataRecord.intake_id != exclude_intake_id,
                NewsArticleMetadataRecord.status.in_(
                    [
                        NewsMetadataStatus.EXTRACTED.value,
                        NewsMetadataStatus.MANUAL.value,
                    ]
                ),
                NewsArticleMetadataRecord.title.is_not(None),
                NewsArticleMetadataRecord.published_at.is_not(None),
                NewsArticleMetadataRecord.published_at >= published_since,
                NewsArticleMetadataRecord.published_at <= published_until,
            )
            .order_by(
                NewsArticleMetadataRecord.published_at.desc(),
                NewsArticleMetadataRecord.intake_id.asc(),
            )
            .limit(limit)
        )

        rows = self._session.execute(statement).all()

        items: list[RecentNewsContextItem] = []

        for row in rows:
            if row.title is None or row.published_at is None:
                continue

            items.append(
                RecentNewsContextItem(
                    intake_id=row.intake_id,
                    source_id=row.source_id,
                    canonical_url=row.canonical_url,
                    title=row.title,
                    description=row.description,
                    published_at=_as_utc(row.published_at),
                )
            )

        return items


class SessionFactoryRecentNewsContextRepository:
    """Read recent context using a short-lived database session."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
    ) -> None:
        self._session_factory = session_factory

    def list_recent_context(
        self,
        *,
        exclude_intake_id: UUID,
        published_since: datetime,
        published_until: datetime,
        limit: int = 50,
    ) -> list[RecentNewsContextItem]:
        with self._session_factory() as session:
            repository = SqlAlchemyRecentNewsContextRepository(session)

            return repository.list_recent_context(
                exclude_intake_id=exclude_intake_id,
                published_since=published_since,
                published_until=published_until,
                limit=limit,
            )
