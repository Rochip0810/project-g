from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.domain.news import (
    CollectionRequest,
    CollectionStatus,
    NewsSource,
    SourceStatus,
)
from project_g.infrastructure.collectors import (
    GiantsOfficialNewsCollector,
    GiantsOfficialNewsParser,
)
from project_g.ports.http import (
    HttpResponse,
    HttpStatusError,
    HttpTimeoutError,
)

FIXTURE_PATH = Path("tests/fixtures/giants_official_news.html")


def _source() -> NewsSource:
    source = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )

    return replace(
        source,
        status=SourceStatus.ENABLED,
    )


class FakeHttpClient:
    def __init__(
        self,
        response: HttpResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        self.calls += 1

        assert url == "https://www.giants.jp/news/"
        assert timeout_seconds == 10
        assert max_response_bytes == 2_000_000
        assert "www.giants.jp" in allowed_hosts

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("Fake response is missing")

        return self.response


def _clock() -> Iterator[datetime]:
    yield datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    yield datetime(2026, 7, 31, 12, 0, 1, tzinfo=UTC)
    yield datetime(2026, 7, 31, 12, 0, 2, tzinfo=UTC)


def _collector(
    client: FakeHttpClient,
) -> GiantsOfficialNewsCollector:
    times = _clock()

    return GiantsOfficialNewsCollector(
        source=_source(),
        http_client=client,
        parser=GiantsOfficialNewsParser(),
        max_response_bytes=2_000_000,
        clock=lambda: next(times),
    )


def test_collector_returns_successful_result() -> None:
    html = FIXTURE_PATH.read_bytes()
    client = FakeHttpClient(
        HttpResponse(
            requested_url="https://www.giants.jp/news/",
            final_url="https://www.giants.jp/news/",
            status_code=200,
            headers={"content-type": "text/html"},
            body=html,
        )
    )

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
            max_items=2,
        )
    )

    assert result.status is CollectionStatus.SUCCEEDED
    assert len(result.items) == 2
    assert client.calls == 1


def test_collector_returns_empty_result() -> None:
    client = FakeHttpClient(
        HttpResponse(
            requested_url="https://www.giants.jp/news/",
            final_url="https://www.giants.jp/news/",
            status_code=200,
            headers={"content-type": "text/html"},
            body=b"<html><body>No news</body></html>",
        )
    )

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
        )
    )

    assert result.status is CollectionStatus.EMPTY
    assert result.items == ()


def test_collector_maps_timeout_to_retryable_failure() -> None:
    client = FakeHttpClient(error=HttpTimeoutError("timeout"))

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
        )
    )

    assert result.status is CollectionStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "SOURCE_TIMEOUT"
    assert result.failure.retryable is True


def test_collector_rejects_non_html_response() -> None:
    client = FakeHttpClient(
        HttpResponse(
            requested_url="https://www.giants.jp/news/",
            final_url="https://www.giants.jp/news/",
            status_code=200,
            headers={"content-type": "application/json"},
            body=b"{}",
        )
    )

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
        )
    )

    assert result.status is CollectionStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == ("SOURCE_CONTENT_TYPE_INVALID")
    assert result.failure.retryable is False


def test_collector_maps_forbidden_status_to_non_retryable_failure() -> None:
    client = FakeHttpClient(
        error=HttpStatusError(
            403,
            "https://www.giants.jp/news/",
        )
    )

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
        )
    )

    assert result.status is CollectionStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "SOURCE_HTTP_STATUS"
    assert result.failure.retryable is False
