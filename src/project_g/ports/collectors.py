from typing import Protocol, runtime_checkable

from project_g.domain.news import (
    CollectionRequest,
    CollectionResult,
    NewsSource,
)


@runtime_checkable
class NewsCollector(Protocol):
    @property
    def source(self) -> NewsSource:
        pass

    def collect(
        self,
        request: CollectionRequest,
    ) -> CollectionResult:
        pass
