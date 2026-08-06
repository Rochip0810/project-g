from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataNotFoundError,
    NewsArticleMetadataRepository,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _get_metadata(
    *,
    repository: NewsArticleMetadataRepository,
    metadata_id: UUID,
) -> NewsArticleMetadata:
    metadata = repository.get_by_metadata_id(metadata_id)

    if metadata is None:
        raise NewsArticleMetadataNotFoundError(metadata_id)

    return metadata


class RecordExtractedNewsArticleMetadata:
    def __init__(
        self,
        *,
        repository: NewsArticleMetadataRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        metadata_id: UUID,
        title: str,
        published_at: datetime | None,
        description: str | None,
    ) -> NewsArticleMetadata:
        metadata = _get_metadata(
            repository=self._repository,
            metadata_id=metadata_id,
        )

        updated = metadata.record_extracted(
            title=title,
            published_at=published_at,
            description=description,
            updated_at=self._clock(),
        )

        return self._repository.update(updated)


class RecordManualNewsArticleMetadata:
    def __init__(
        self,
        *,
        repository: NewsArticleMetadataRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        metadata_id: UUID,
        title: str,
        published_at: datetime | None,
        description: str | None,
    ) -> NewsArticleMetadata:
        metadata = _get_metadata(
            repository=self._repository,
            metadata_id=metadata_id,
        )

        updated = metadata.record_manual(
            title=title,
            published_at=published_at,
            description=description,
            updated_at=self._clock(),
        )

        return self._repository.update(updated)


class MarkNewsArticleMetadataUnavailable:
    def __init__(
        self,
        *,
        repository: NewsArticleMetadataRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        metadata_id: UUID,
        reason: str,
    ) -> NewsArticleMetadata:
        metadata = _get_metadata(
            repository=self._repository,
            metadata_id=metadata_id,
        )

        updated = metadata.mark_unavailable(
            reason=reason,
            updated_at=self._clock(),
        )

        return self._repository.update(updated)


class MarkNewsArticleMetadataFailed:
    def __init__(
        self,
        *,
        repository: NewsArticleMetadataRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        metadata_id: UUID,
        reason: str,
    ) -> NewsArticleMetadata:
        metadata = _get_metadata(
            repository=self._repository,
            metadata_id=metadata_id,
        )

        updated = metadata.mark_failed(
            reason=reason,
            updated_at=self._clock(),
        )

        return self._repository.update(updated)
