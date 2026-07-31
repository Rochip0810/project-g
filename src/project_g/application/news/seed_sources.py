from dataclasses import dataclass

from project_g.application.news.initial_sources import (
    INITIAL_NEWS_SOURCES,
)
from project_g.domain.news import NewsSource
from project_g.ports.repositories import NewsSourceRepository


class InitialNewsSourceConflictError(ValueError):
    def __init__(
        self,
        *,
        expected: NewsSource,
        stored: NewsSource,
    ) -> None:
        super().__init__(
            f"Stored news source conflicts with the approved catalog: {expected.source_id}"
        )
        self.expected = expected
        self.stored = stored


@dataclass(frozen=True, slots=True)
class SourceSeedResult:
    added_source_ids: tuple[str, ...]
    existing_source_ids: tuple[str, ...]

    @property
    def added_count(self) -> int:
        return len(self.added_source_ids)

    @property
    def existing_count(self) -> int:
        return len(self.existing_source_ids)

    @property
    def total_count(self) -> int:
        return self.added_count + self.existing_count


def seed_initial_news_sources(
    repository: NewsSourceRepository,
) -> SourceSeedResult:
    added_source_ids: list[str] = []
    existing_source_ids: list[str] = []

    for expected_source in INITIAL_NEWS_SOURCES:
        stored_source = repository.get_by_source_id(expected_source.source_id)

        if stored_source is None:
            repository.add(expected_source)
            added_source_ids.append(expected_source.source_id)
            continue

        if stored_source != expected_source:
            raise InitialNewsSourceConflictError(
                expected=expected_source,
                stored=stored_source,
            )

        existing_source_ids.append(expected_source.source_id)

    return SourceSeedResult(
        added_source_ids=tuple(added_source_ids),
        existing_source_ids=tuple(existing_source_ids),
    )
