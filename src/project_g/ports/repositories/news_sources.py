from typing import Protocol, runtime_checkable

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
)


class NewsSourceAlreadyExistsError(ValueError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"News source already exists: {source_id}")
        self.source_id = source_id


class StoredNewsSourceNotFoundError(LookupError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"Stored news source was not found: {source_id}")
        self.source_id = source_id


@runtime_checkable
class NewsSourceRepository(Protocol):
    def add(self, source: NewsSource) -> NewsSource:
        pass

    def get_by_source_id(
        self,
        source_id: str,
    ) -> NewsSource | None:
        pass

    def list_all(self) -> tuple[NewsSource, ...]:
        pass

    def list_collectable(self) -> tuple[NewsSource, ...]:
        pass

    def update_status(
        self,
        source_id: str,
        status: SourceStatus,
    ) -> NewsSource:
        pass
