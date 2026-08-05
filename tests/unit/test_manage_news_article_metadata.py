from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.manage_article_metadata import (
    MarkNewsArticleMetadataFailed,
    MarkNewsArticleMetadataUnavailable,
    RecordExtractedNewsArticleMetadata,
    RecordManualNewsArticleMetadata,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataAlreadyExistsError,
    NewsArticleMetadataNotFoundError,
)

_METADATA_ID = UUID("90037762-b5db-4306-8303-d339590b6f25")
_UNKNOWN_METADATA_ID = UUID("52f877e5-0af7-4458-8237-21e7187262e1")
_INTAKE_ID = UUID("c324d025-f14c-4855-922f-c54f0cbc46ce")

_CREATED_AT = datetime(
    2026,
    8,
    5,
    16,
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


class FakeNewsArticleMetadataRepository:
    def __init__(
        self,
        metadata: NewsArticleMetadata | None = None,
    ) -> None:
        self._by_metadata_id: dict[
            UUID,
            NewsArticleMetadata,
        ] = {}
        self._by_intake_id: dict[
            UUID,
            NewsArticleMetadata,
        ] = {}
        self.updated: list[NewsArticleMetadata] = []

        if metadata is not None:
            self._by_metadata_id[metadata.metadata_id] = metadata
            self._by_intake_id[metadata.intake_id] = metadata

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        if metadata.intake_id in self._by_intake_id:
            raise NewsArticleMetadataAlreadyExistsError(metadata.intake_id)

        self._by_metadata_id[metadata.metadata_id] = metadata
        self._by_intake_id[metadata.intake_id] = metadata

        return metadata

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        if metadata.metadata_id not in self._by_metadata_id:
            raise NewsArticleMetadataNotFoundError(metadata.metadata_id)

        self._by_metadata_id[metadata.metadata_id] = metadata
        self._by_intake_id[metadata.intake_id] = metadata
        self.updated.append(metadata)

        return metadata

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        return self._by_metadata_id.get(metadata_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        return self._by_intake_id.get(intake_id)


def _pending() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_service_records_extracted_metadata() -> None:
    repository = FakeNewsArticleMetadataRepository(_pending())

    metadata = RecordExtractedNewsArticleMetadata(
        repository=repository,
        clock=lambda: _UPDATED_AT,
    ).execute(
        metadata_id=_METADATA_ID,
        title="Extracted article title",
        published_at=_PUBLISHED_AT,
        description="Extracted description.",
    )

    assert metadata.status is NewsMetadataStatus.EXTRACTED
    assert metadata.title == "Extracted article title"
    assert metadata.published_at == _PUBLISHED_AT
    assert repository.updated == [metadata]


def test_service_records_manual_metadata() -> None:
    repository = FakeNewsArticleMetadataRepository(_pending())

    metadata = RecordManualNewsArticleMetadata(
        repository=repository,
        clock=lambda: _UPDATED_AT,
    ).execute(
        metadata_id=_METADATA_ID,
        title="  Manually entered title  ",
        published_at=None,
        description=None,
    )

    assert metadata.status is NewsMetadataStatus.MANUAL
    assert metadata.title == "Manually entered title"
    assert metadata.updated_at == _UPDATED_AT


def test_service_marks_metadata_unavailable() -> None:
    repository = FakeNewsArticleMetadataRepository(_pending())

    metadata = MarkNewsArticleMetadataUnavailable(
        repository=repository,
        clock=lambda: _UPDATED_AT,
    ).execute(
        metadata_id=_METADATA_ID,
        reason="Source returned HTTP 403",
    )

    assert metadata.status is NewsMetadataStatus.UNAVAILABLE
    assert metadata.failure_reason == ("Source returned HTTP 403")


def test_service_marks_metadata_failed() -> None:
    repository = FakeNewsArticleMetadataRepository(_pending())

    metadata = MarkNewsArticleMetadataFailed(
        repository=repository,
        clock=lambda: _UPDATED_AT,
    ).execute(
        metadata_id=_METADATA_ID,
        reason="Metadata parser failed",
    )

    assert metadata.status is NewsMetadataStatus.FAILED
    assert metadata.failure_reason == ("Metadata parser failed")


def test_service_rejects_unknown_metadata() -> None:
    repository = FakeNewsArticleMetadataRepository()

    with pytest.raises(NewsArticleMetadataNotFoundError):
        RecordManualNewsArticleMetadata(
            repository=repository,
            clock=lambda: _UPDATED_AT,
        ).execute(
            metadata_id=_UNKNOWN_METADATA_ID,
            title="Manual title",
            published_at=None,
            description=None,
        )
