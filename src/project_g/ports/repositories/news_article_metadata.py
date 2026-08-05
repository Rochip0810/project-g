from typing import Protocol
from uuid import UUID

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)


class NewsArticleMetadataAlreadyExistsError(RuntimeError):
    """Raised when an intake already has metadata."""

    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Article metadata already exists for intake: {intake_id}")
        self.intake_id = intake_id


class NewsArticleMetadataNotFoundError(RuntimeError):
    """Raised when article metadata cannot be found."""

    def __init__(self, metadata_id: UUID) -> None:
        super().__init__(f"Article metadata was not found: {metadata_id}")
        self.metadata_id = metadata_id


class NewsArticleMetadataRepository(Protocol):
    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        """Store and return new article metadata."""
        ...

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        """Update and return existing article metadata."""
        ...

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        """Return article metadata by its ID."""
        ...

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        """Return article metadata associated with an intake."""
        ...
