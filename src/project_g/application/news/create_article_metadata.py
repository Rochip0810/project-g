from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataAlreadyExistsError,
    NewsArticleMetadataRepository,
)

Clock = Callable[[], datetime]
MetadataIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateNewsArticleMetadata:
    def __init__(
        self,
        *,
        repository: NewsArticleMetadataRepository,
        clock: Clock = _utc_now,
        metadata_id_factory: MetadataIdFactory = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._metadata_id_factory = metadata_id_factory

    def execute(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata:
        existing = self._repository.get_by_intake_id(intake_id)

        if existing is not None:
            raise NewsArticleMetadataAlreadyExistsError(intake_id)

        metadata = NewsArticleMetadata.pending(
            metadata_id=self._metadata_id_factory(),
            intake_id=intake_id,
            created_at=self._clock(),
        )

        return self._repository.add(metadata)
