from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.article_metadata import (
    InvalidNewsArticleMetadataError,
    InvalidNewsMetadataTransitionError,
    NewsArticleMetadata,
    NewsMetadataStatus,
)

_METADATA_ID = UUID("cd979fd9-9ce5-45a4-b4a1-b839309206c3")
_INTAKE_ID = UUID("b4916047-8404-4abc-af7c-2e48588fb145")
_CREATED_AT = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)
_PUBLISHED_AT = datetime(2026, 8, 5, 9, 0, tzinfo=UTC)


def _pending() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_pending_factory_creates_empty_metadata() -> None:
    metadata = _pending()

    assert metadata.status is NewsMetadataStatus.PENDING
    assert metadata.title is None
    assert metadata.published_at is None
    assert metadata.description is None
    assert metadata.failure_reason is None


def test_pending_metadata_can_record_extracted_data() -> None:
    metadata = _pending().record_extracted(
        title="  Giants announce roster update  ",
        published_at=_PUBLISHED_AT,
        description="  Official team announcement.  ",
        updated_at=_UPDATED_AT,
    )

    assert metadata.status is NewsMetadataStatus.EXTRACTED
    assert metadata.title == "Giants announce roster update"
    assert metadata.description == "Official team announcement."
    assert metadata.published_at == _PUBLISHED_AT


def test_pending_metadata_can_record_manual_data() -> None:
    metadata = _pending().record_manual(
        title="Manual article title",
        published_at=None,
        description=None,
        updated_at=_UPDATED_AT,
    )

    assert metadata.status is NewsMetadataStatus.MANUAL
    assert metadata.title == "Manual article title"
    assert metadata.published_at is None


def test_pending_metadata_can_be_marked_unavailable() -> None:
    metadata = _pending().mark_unavailable(
        reason="  Source returned HTTP 403  ",
        updated_at=_UPDATED_AT,
    )

    assert metadata.status is NewsMetadataStatus.UNAVAILABLE
    assert metadata.failure_reason == "Source returned HTTP 403"


def test_pending_metadata_can_be_marked_failed() -> None:
    metadata = _pending().mark_failed(
        reason="Metadata parser failed",
        updated_at=_UPDATED_AT,
    )

    assert metadata.status is NewsMetadataStatus.FAILED
    assert metadata.failure_reason == "Metadata parser failed"


def test_extracted_metadata_cannot_transition_again() -> None:
    metadata = _pending().record_extracted(
        title="Extracted title",
        published_at=None,
        description=None,
        updated_at=_UPDATED_AT,
    )

    with pytest.raises(
        InvalidNewsMetadataTransitionError,
        match="pending or unavailable",
    ):
        metadata.record_manual(
            title="Later title",
            published_at=None,
            description=None,
            updated_at=_UPDATED_AT + timedelta(minutes=1),
        )


def test_extracted_metadata_requires_title() -> None:
    with pytest.raises(
        InvalidNewsArticleMetadataError,
        match="must include a title",
    ):
        _pending().record_extracted(
            title="   ",
            published_at=None,
            description=None,
            updated_at=_UPDATED_AT,
        )


def test_metadata_rejects_naive_published_at() -> None:
    with pytest.raises(
        InvalidNewsArticleMetadataError,
        match="published_at must be timezone-aware",
    ):
        _pending().record_manual(
            title="Manual title",
            published_at=datetime(2026, 8, 5, 9, 0),
            description=None,
            updated_at=_UPDATED_AT,
        )


def test_metadata_rejects_oversized_description() -> None:
    with pytest.raises(
        InvalidNewsArticleMetadataError,
        match="description must not exceed 2000",
    ):
        _pending().record_manual(
            title="Manual title",
            published_at=None,
            description="x" * 2001,
            updated_at=_UPDATED_AT,
        )


def test_metadata_rejects_updated_at_before_creation() -> None:
    with pytest.raises(
        InvalidNewsArticleMetadataError,
        match="updated_at must not be earlier",
    ):
        _pending().mark_failed(
            reason="Failed",
            updated_at=_CREATED_AT - timedelta(seconds=1),
        )


def test_unavailable_metadata_can_be_replaced_manually() -> None:
    unavailable = _pending().mark_unavailable(
        reason="Source returned HTTP 403",
        updated_at=_UPDATED_AT,
    )

    manual = unavailable.record_manual(
        title="Manually confirmed title",
        published_at=_PUBLISHED_AT,
        description=None,
        updated_at=_UPDATED_AT + timedelta(minutes=1),
    )

    assert manual.status is NewsMetadataStatus.MANUAL
    assert manual.title == "Manually confirmed title"
    assert manual.failure_reason is None
