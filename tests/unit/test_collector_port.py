from datetime import UTC, datetime

from project_g.domain.news import (
    CollectionRequest,
    CollectionResult,
    NewsSource,
    SourceType,
)
from project_g.ports import NewsCollector


class FakeNewsCollector:
    def __init__(self, source: NewsSource) -> None:
        self._source = source

    @property
    def source(self) -> NewsSource:
        return self._source

    def collect(
        self,
        request: CollectionRequest,
    ) -> CollectionResult:
        now = datetime.now(UTC)

        return CollectionResult.empty(
            source=request.source,
            started_at=now,
            completed_at=now,
        )


def test_collector_implements_common_interface() -> None:
    source = NewsSource(
        source_id="giants_official",
        name="Giants Official",
        source_type=SourceType.WEBSITE,
        base_url="https://example.com/giants",
        is_official=True,
        priority=100,
    )
    collector = FakeNewsCollector(source)

    assert isinstance(collector, NewsCollector)

    result = collector.collect(
        CollectionRequest(
            source=source,
            timeout_seconds=10,
        )
    )

    assert result.source == source
    assert result.items == ()
