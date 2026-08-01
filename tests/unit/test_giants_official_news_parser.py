from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.domain.news import NewsSource
from project_g.infrastructure.collectors import (
    GiantsOfficialNewsParser,
)

FIXTURE_PATH = Path("tests/fixtures/giants_official_news.html")


def _source() -> NewsSource:
    return next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )


def test_parser_extracts_news_metadata() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    collected_at = datetime(
        2026,
        7,
        31,
        12,
        0,
        tzinfo=UTC,
    )

    items = GiantsOfficialNewsParser().parse(
        html,
        source=_source(),
        collected_at=collected_at,
        max_items=50,
    )

    assert len(items) == 3

    first = items[0]

    assert first.title == "新外国人選手の入団を発表"
    assert first.source_url == ("https://www.giants.jp/news/12345/")
    assert first.canonical_url == ("https://www.giants.jp/news/12345/")
    assert first.external_id == "12345"
    assert first.collected_at == collected_at
    assert first.published_at == datetime(
        2026,
        7,
        31,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_parser_normalizes_urls_and_removes_duplicates() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    items = GiantsOfficialNewsParser().parse(
        html,
        source=_source(),
        collected_at=datetime.now(UTC),
        max_items=50,
    )

    urls = tuple(item.canonical_url for item in items)

    assert urls == (
        "https://www.giants.jp/news/12345/",
        "https://www.giants.jp/news/12344/",
        "https://www.giants.jp/news/12343/",
    )
    assert len(urls) == len(set(urls))


def test_parser_rejects_external_and_non_article_links() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    items = GiantsOfficialNewsParser().parse(
        html,
        source=_source(),
        collected_at=datetime.now(UTC),
        max_items=50,
    )

    assert all(item.canonical_url.startswith("https://www.giants.jp/news/") for item in items)
    assert all("example.com" not in item.canonical_url for item in items)


def test_parser_respects_max_items() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    items = GiantsOfficialNewsParser().parse(
        html,
        source=_source(),
        collected_at=datetime.now(UTC),
        max_items=2,
    )

    assert len(items) == 2


def test_parser_returns_empty_for_unrecognized_html() -> None:
    items = GiantsOfficialNewsParser().parse(
        "<html><body>No news</body></html>",
        source=_source(),
        collected_at=datetime.now(UTC),
        max_items=50,
    )

    assert items == ()
