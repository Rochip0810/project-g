from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.create_article_metadata import (
    CreateNewsArticleMetadata,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataAlreadyExistsError,
    NewsArticleMetadataNotFoundError,
)

_METADATA_ID = UUID("aa183043-2282-43c8-b63a-a83240b2300e")
_INTAKE_ID = UUID("070aff1d-d13f-4acb-9f33-69366bbab990")
_CREATED_AT = datetime(
    2026,
    8,
    5,
    13,
    0,
    tzinfo=UTC,
)


class FakeNewsArticleMetadataRepository:
    def __init__(self) -> None:
        self._by_metadata_id: dict[
            UUID,
            NewsArticleMetadata,
        ] = {}
        self._by_intake_id: dict[
            UUID,
            NewsArticleMetadata,
        ] = {}
        self.added: list[NewsArticleMetadata] = []

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        if metadata.intake_id in self._by_intake_id:
            raise NewsArticleMetadataAlreadyExistsError(metadata.intake_id)

        self._by_metadata_id[metadata.metadata_id] = metadata
        self._by_intake_id[metadata.intake_id] = metadata
        self.added.append(metadata)

        return metadata

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        if metadata.metadata_id not in self._by_metadata_id:
            raise NewsArticleMetadataNotFoundError(metadata.metadata_id)

        self._by_metadata_id[metadata.metadata_id] = metadata
        self._by_intake_id[metadata.intake_id] = metadata

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


def _service(
    repository: FakeNewsArticleMetadataRepository,
) -> CreateNewsArticleMetadata:
    return CreateNewsArticleMetadata(
        repository=repository,
        clock=lambda: _CREATED_AT,
        metadata_id_factory=lambda: _METADATA_ID,
    )


def test_service_creates_pending_metadata() -> None:
    repository = FakeNewsArticleMetadataRepository()

    metadata = _service(repository).execute(_INTAKE_ID)

    assert metadata.metadata_id == _METADATA_ID
    assert metadata.intake_id == _INTAKE_ID
    assert metadata.status is NewsMetadataStatus.PENDING
    assert metadata.created_at == _CREATED_AT
    assert metadata.updated_at == _CREATED_AT
    assert repository.added == [metadata]


def test_service_rejects_duplicate_intake_metadata() -> None:
    repository = FakeNewsArticleMetadataRepository()
    service = _service(repository)

    first = service.execute(_INTAKE_ID)

    with pytest.raises(
        NewsArticleMetadataAlreadyExistsError,
        match="already exists",
    ):
        service.execute(_INTAKE_ID)

    assert repository.added == [first]


def test_repository_returns_metadata_by_intake() -> None:
    repository = FakeNewsArticleMetadataRepository()

    created = _service(repository).execute(_INTAKE_ID)

    assert repository.get_by_intake_id(_INTAKE_ID) == created
    assert repository.get_by_metadata_id(_METADATA_ID) == created
