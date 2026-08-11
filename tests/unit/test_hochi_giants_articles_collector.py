from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.domain.news import (
    CollectionRequest,
    CollectionStatus,
    NewsSource,
    SourceStatus,
)
from project_g.infrastructure.collectors import (
    HochiGiantsArticlesCollector,
    HochiGiantsArticlesParser,
)
from project_g.ports.http import (
    HttpResponse,
    HttpStatusError,
)

_HTML = """
<html>
<body>
<a href="/articles/20260811-OHT1T51258.html">
【巨人】山の日主催試合で今季最多
2026年08月11日 18:30
</a>

<a href="https://hochi.news/articles/20260811-OHT1T51256.html">
【巨人】山崎伊織が６失点
2026年08月11日 18:27
</a>

<a href="/baseball/">
野球
</a>
</body>
</html>
"""


def _source() -> NewsSource:
    source = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "hochi_giants_articles"
    )

    return replace(
        source,
        status=SourceStatus.ENABLED,
    )


def _clock() -> Iterator[datetime]:
    yield datetime(
        2026,
        8,
        11,
        9,
        0,
        tzinfo=UTC,
    )
    yield datetime(
        2026,
        8,
        11,
        9,
        0,
        1,
        tzinfo=UTC,
    )
    yield datetime(
        2026,
        8,
        11,
        9,
        0,
        2,
        tzinfo=UTC,
    )


class FakeHttpClient:
    def __init__(
        self,
        *,
        response: HttpResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        assert url == ("https://hochi.news/tag/%E5%B7%A8%E4%BA%BA")
        assert timeout_seconds == 10
        assert max_response_bytes == 500_000
        assert "hochi.news" in allowed_hosts

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("Fake response is missing")

        return self.response


def _collector(
    client: FakeHttpClient,
) -> HochiGiantsArticlesCollector:
    times = _clock()

    return HochiGiantsArticlesCollector(
        source=_source(),
        http_client=client,
        parser=HochiGiantsArticlesParser(),
        max_response_bytes=500_000,
        clock=lambda: next(times),
    )


def test_parser_extracts_hochi_articles() -> None:
    parser = HochiGiantsArticlesParser()

    items = parser.parse(
        _HTML,
        source=_source(),
        collected_at=datetime(
            2026,
            8,
            11,
            9,
            0,
            tzinfo=UTC,
        ),
        max_items=10,
    )

    assert len(items) == 2

    first = items[0]

    assert first.title == ("【巨人】山の日主催試合で今季最多")
    assert first.canonical_url == ("https://hochi.news/articles/20260811-OHT1T51258.html")
    assert first.external_id == ("20260811-OHT1T51258")
    assert first.published_at is not None
    assert first.published_at.isoformat() == ("2026-08-11T18:30:00+09:00")


def test_collector_returns_success() -> None:
    client = FakeHttpClient(
        response=HttpResponse(
            requested_url=("https://hochi.news/tag/%E5%B7%A8%E4%BA%BA"),
            final_url=("https://hochi.news/tag/%E5%B7%A8%E4%BA%BA"),
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=_HTML.encode(),
        )
    )

    result = _collector(client).collect(
        CollectionRequest(
            source=_source(),
            timeout_seconds=10,
            max_items=10,
        )
    )

    assert result.status is CollectionStatus.SUCCEEDED
    assert len(result.items) == 2


def test_collector_maps_http_403_to_failure() -> None:
    client = FakeHttpClient(
        error=HttpStatusError(
            403,
            ("https://hochi.news/tag/%E5%B7%A8%E4%BA%BA"),
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
