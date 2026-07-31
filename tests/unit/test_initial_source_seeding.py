from dataclasses import replace

import pytest

from project_g.application.news import (
    INITIAL_NEWS_SOURCES,
    InitialNewsSourceConflictError,
    seed_initial_news_sources,
)
from project_g.domain.news import (
    NewsSource,
    SourceStatus,
)
from project_g.ports.repositories import (
    NewsSourceAlreadyExistsError,
    StoredNewsSourceNotFoundError,
)


class InMemoryNewsSourceRepository:
    def __init__(self) -> None:
        self.sources: dict[str, NewsSource] = {}

    def add(self, source: NewsSource) -> NewsSource:
        if source.source_id in self.sources:
            raise NewsSourceAlreadyExistsError(source.source_id)

        self.sources[source.source_id] = source
        return source

    def get_by_source_id(
        self,
        source_id: str,
    ) -> NewsSource | None:
        return self.sources.get(source_id)

    def list_all(self) -> tuple[NewsSource, ...]:
        return tuple(
            sorted(
                self.sources.values(),
                key=lambda source: source.source_id,
            )
        )

    def list_collectable(self) -> tuple[NewsSource, ...]:
        return tuple(
            sorted(
                (source for source in self.sources.values() if source.collectable),
                key=lambda source: (
                    not source.is_official,
                    -source.priority,
                    source.name.casefold(),
                ),
            )
        )

    def update_status(
        self,
        source_id: str,
        status: SourceStatus,
    ) -> NewsSource:
        current = self.sources.get(source_id)

        if current is None:
            raise StoredNewsSourceNotFoundError(source_id)

        updated = replace(current, status=status)
        self.sources[source_id] = updated

        return updated


def test_initial_source_seeding_adds_seven_sources() -> None:
    repository = InMemoryNewsSourceRepository()

    result = seed_initial_news_sources(repository)

    assert result.added_count == 7
    assert result.existing_count == 0
    assert result.total_count == 7
    assert len(repository.sources) == 7


def test_initial_source_seeding_is_idempotent() -> None:
    repository = InMemoryNewsSourceRepository()

    first_result = seed_initial_news_sources(repository)
    second_result = seed_initial_news_sources(repository)

    assert first_result.added_count == 7
    assert second_result.added_count == 0
    assert second_result.existing_count == 7
    assert len(repository.sources) == 7


def test_conflicting_existing_source_is_rejected() -> None:
    repository = InMemoryNewsSourceRepository()
    expected = INITIAL_NEWS_SOURCES[0]

    repository.add(
        replace(
            expected,
            priority=99,
        )
    )

    with pytest.raises(InitialNewsSourceConflictError):
        seed_initial_news_sources(repository)
