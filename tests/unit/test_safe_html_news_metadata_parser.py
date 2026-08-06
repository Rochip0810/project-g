from datetime import UTC, datetime

import pytest

from project_g.infrastructure.news_metadata import (
    MAX_HTML_CHARACTERS,
    SafeHtmlNewsMetadataParser,
)
from project_g.ports.news_metadata import (
    NewsMetadataExtractionError,
)


def test_parser_extracts_open_graph_metadata() -> None:
    html = """
    <html>
      <head>
        <title>Fallback title</title>
        <meta
          property="og:title"
          content="Giants announce roster update"
        >
        <meta
          property="og:description"
          content="Official team announcement."
        >
        <meta
          property="article:published_time"
          content="2026-08-05T18:00:00+09:00"
        >
      </head>
      <body>Article body must not be stored.</body>
    </html>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.title == ("Giants announce roster update")
    assert result.description == ("Official team announcement.")
    assert result.published_at == datetime(
        2026,
        8,
        5,
        9,
        0,
        tzinfo=UTC,
    )


def test_parser_falls_back_to_html_title() -> None:
    html = """
    <html>
      <head>
        <title>
          Giants &amp; Tigers game information
        </title>
        <meta
          name="description"
          content="Game information."
        >
      </head>
    </html>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.title == ("Giants & Tigers game information")
    assert result.description == "Game information."
    assert result.published_at is None


def test_parser_accepts_twitter_metadata() -> None:
    html = """
    <head>
      <meta
        name="twitter:title"
        content="Giants Twitter title"
      >
      <meta
        name="twitter:description"
        content="Twitter description."
      >
    </head>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.title == "Giants Twitter title"
    assert result.description == "Twitter description."


def test_parser_accepts_itemprop_publication_time() -> None:
    html = """
    <head>
      <title>Giants article</title>
      <meta
        itemprop="datePublished"
        content="2026-08-05T09:00:00Z"
      >
    </head>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.published_at == datetime(
        2026,
        8,
        5,
        9,
        0,
        tzinfo=UTC,
    )


def test_parser_ignores_invalid_publication_time() -> None:
    html = """
    <head>
      <title>Giants article</title>
      <meta
        property="article:published_time"
        content="not-a-datetime"
      >
    </head>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.published_at is None


def test_parser_ignores_metadata_inside_body() -> None:
    html = """
    <html>
      <head>
        <title>Safe head title</title>
      </head>
      <body>
        <meta
          property="og:title"
          content="Unsafe body title"
        >
      </body>
    </html>
    """

    result = SafeHtmlNewsMetadataParser().parse(html)

    assert result.title == "Safe head title"


def test_parser_rejects_missing_title() -> None:
    html = """
    <html>
      <head>
        <meta
          name="description"
          content="Description only."
        >
      </head>
    </html>
    """

    with pytest.raises(
        NewsMetadataExtractionError,
        match="title was not found",
    ):
        SafeHtmlNewsMetadataParser().parse(html)


def test_parser_rejects_oversized_html() -> None:
    html = "x" * (MAX_HTML_CHARACTERS + 1)

    with pytest.raises(
        NewsMetadataExtractionError,
        match="safe metadata parsing limit",
    ):
        SafeHtmlNewsMetadataParser().parse(html)
