import pytest

from project_g.application.news.initial_sources import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.manual_url import (
    ManualNewsUrlResolver,
    UnsafeManualNewsUrlError,
    UnsupportedNewsSourceError,
)


def _resolver() -> ManualNewsUrlResolver:
    return ManualNewsUrlResolver(INITIAL_NEWS_SOURCES)


def test_resolver_matches_registered_source() -> None:
    result = _resolver().resolve("https://www.giants.jp/news/12345/")

    assert result.source.source_id == "giants_official_news"
    assert result.canonical_url == "https://www.giants.jp/news/12345/"


def test_resolver_removes_tracking_and_fragment() -> None:
    result = _resolver().resolve(
        "https://www.giants.jp/news/12345/?utm_source=google&category=team&fbclid=tracking#details"
    )

    assert result.canonical_url == ("https://www.giants.jp/news/12345/?category=team")


def test_resolver_sorts_remaining_query_parameters() -> None:
    result = _resolver().resolve("https://www.giants.jp/news/12345/?z=2&a=1")

    assert result.canonical_url == ("https://www.giants.jp/news/12345/?a=1&z=2")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.giants.jp/news/12345/",
        "ftp://www.giants.jp/news/12345/",
        "https://user:password@www.giants.jp/news/12345/",
        "https://www.giants.jp:8443/news/12345/",
        "https://localhost/news/12345/",
        "https://service.internal/news/12345/",
        "https://127.0.0.1/news/12345/",
        "https://192.168.1.10/news/12345/",
    ],
)
def test_resolver_rejects_unsafe_urls(
    url: str,
) -> None:
    with pytest.raises(UnsafeManualNewsUrlError):
        _resolver().resolve(url)


def test_resolver_rejects_unregistered_hostname() -> None:
    with pytest.raises(UnsupportedNewsSourceError):
        _resolver().resolve("https://example.org/news/12345/")


def test_resolver_rejects_unregistered_source_path() -> None:
    with pytest.raises(UnsupportedNewsSourceError):
        _resolver().resolve("https://www.giants.jp/unknown/12345/")


def test_paused_source_can_still_be_used_for_manual_intake() -> None:
    result = _resolver().resolve("https://www.giants.jp/news/12345/")

    assert result.source.source_id == "giants_official_news"
    assert result.source.collectable is False
