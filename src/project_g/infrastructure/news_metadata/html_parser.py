from datetime import UTC, datetime
from html.parser import HTMLParser

from project_g.ports.news_metadata import (
    ExtractedNewsMetadata,
    NewsMetadataExtractionError,
)

MAX_HTML_CHARACTERS = 1_000_000

_TITLE_KEYS = (
    "og:title",
    "twitter:title",
)
_DESCRIPTION_KEYS = (
    "og:description",
    "twitter:description",
    "description",
)
_PUBLISHED_AT_KEYS = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "date",
)


def _normalize_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = " ".join(value.split())

    return normalized or None


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    normalized = _normalize_text(value)

    if normalized is None:
        return None

    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None

    return parsed.astimezone(UTC)


class _HeadMetadataCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._accepting_head_content = True
        self._inside_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()

        if normalized_tag == "body":
            self._accepting_head_content = False
            self._inside_title = False
            return

        if not self._accepting_head_content:
            return

        if normalized_tag == "title":
            self._inside_title = True
            return

        if normalized_tag != "meta":
            return

        attributes = {name.lower(): value for name, value in attrs if value is not None}

        key = attributes.get("property") or attributes.get("name") or attributes.get("itemprop")
        content = attributes.get("content")

        normalized_key = _normalize_text(key)
        normalized_content = _normalize_text(content)

        if normalized_key is None or normalized_content is None:
            return

        self.metadata.setdefault(
            normalized_key.lower(),
            normalized_content,
        )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized_tag = tag.lower()

        if normalized_tag == "title":
            self._inside_title = False

        if normalized_tag == "head":
            self._accepting_head_content = False
            self._inside_title = False

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._accepting_head_content and self._inside_title:
            self.title_parts.append(data)


def _first_metadata_value(
    metadata: dict[str, str],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = _normalize_text(metadata.get(key))

        if value is not None:
            return value

    return None


class SafeHtmlNewsMetadataParser:
    def parse(
        self,
        html: str,
    ) -> ExtractedNewsMetadata:
        if len(html) > MAX_HTML_CHARACTERS:
            raise NewsMetadataExtractionError("HTML exceeds the safe metadata parsing limit")

        collector = _HeadMetadataCollector()

        try:
            collector.feed(html)
            collector.close()
        except Exception as error:
            raise NewsMetadataExtractionError("HTML metadata parsing failed") from error

        title = _first_metadata_value(
            collector.metadata,
            _TITLE_KEYS,
        )

        if title is None:
            title = _normalize_text("".join(collector.title_parts))

        if title is None:
            raise NewsMetadataExtractionError("Article title was not found")

        description = _first_metadata_value(
            collector.metadata,
            _DESCRIPTION_KEYS,
        )

        published_at_text = _first_metadata_value(
            collector.metadata,
            _PUBLISHED_AT_KEYS,
        )

        return ExtractedNewsMetadata(
            title=title,
            published_at=_parse_datetime(published_at_text),
            description=description,
        )
