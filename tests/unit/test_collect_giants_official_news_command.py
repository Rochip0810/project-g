from datetime import UTC, datetime
from io import StringIO

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.domain.news import (
    CollectionFailure,
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
    NewsSource,
)
from project_g.interfaces.management.collect_giants_official_news import (
    print_collection_result,
    run_collection,
)


def _source() -> NewsSource:
    return next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )


class FakeCollector:
    def __init__(
        self,
        result: CollectionResult,
    ) -> None:
        self._source = result.source
        self._result = result
        self.last_request: CollectionRequest | None = None

    @property
    def source(self) -> NewsSource:
        return self._source

    def collect(
        self,
        request: CollectionRequest,
    ) -> CollectionResult:
        self.last_request = request
        return self._result


def test_run_collection_creates_expected_request() -> None:
    now = datetime.now(UTC)
    result = CollectionResult.empty(
        source=_source(),
        started_at=now,
        completed_at=now,
    )
    collector = FakeCollector(result)

    returned = run_collection(
        collector,
        timeout_seconds=8,
        max_items=4,
    )

    assert returned is result
    assert collector.last_request is not None
    assert collector.last_request.timeout_seconds == 8
    assert collector.last_request.max_items == 4


def test_print_collection_result_displays_empty_result() -> None:
    now = datetime.now(UTC)
    result = CollectionResult.empty(
        source=_source(),
        started_at=now,
        completed_at=now,
    )
    output = StringIO()

    print_collection_result(
        result,
        output=output,
    )

    text = output.getvalue()

    assert "status=empty" in text
    assert "source_id=giants_official_news" in text
    assert "item_count=0" in text


def test_print_collection_result_displays_failure() -> None:
    now = datetime.now(UTC)
    result = CollectionResult.failed(
        source=_source(),
        failure=CollectionFailure(
            code="SOURCE_TIMEOUT",
            message="The source request timed out",
            retryable=True,
        ),
        started_at=now,
        completed_at=now,
    )
    output = StringIO()

    print_collection_result(
        result,
        output=output,
    )

    text = output.getvalue()

    assert result.status is CollectionStatus.FAILED
    assert "status=failed" in text
    assert "failure_code=SOURCE_TIMEOUT" in text
    assert "retryable=true" in text
