from datetime import UTC, datetime, timedelta
from uuid import UUID

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.infrastructure.database.base import Base
from project_g.infrastructure.database.models.news_article_metadata import (
    NewsArticleMetadataRecord,
)

_METADATA_ID = UUID("bd9b610f-a767-42f3-8578-757fcac17072")
_INTAKE_ID = UUID("85ca30e4-15b7-4be3-968b-b3b6300f6d9b")
_CREATED_AT = datetime(2026, 8, 5, 14, 0, tzinfo=UTC)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)


def _pending() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_news_article_metadata_table_is_registered() -> None:
    assert "news_article_metadata" in Base.metadata.tables


def test_pending_metadata_record_round_trip() -> None:
    metadata = _pending()

    record = NewsArticleMetadataRecord.from_domain(metadata)

    assert record.metadata_id == metadata.metadata_id
    assert record.intake_id == metadata.intake_id
    assert record.status == "pending"
    assert record.to_domain() == metadata


def test_unavailable_metadata_record_round_trip() -> None:
    metadata = _pending().mark_unavailable(
        reason="Source returned HTTP 403",
        updated_at=_UPDATED_AT,
    )

    record = NewsArticleMetadataRecord.from_domain(metadata)

    assert record.status == "unavailable"
    assert record.failure_reason == "Source returned HTTP 403"
    assert record.to_domain() == metadata
