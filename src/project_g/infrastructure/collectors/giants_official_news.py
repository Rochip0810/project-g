import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from project_g.domain.news import (
    CollectedNewsItem,
    CollectionFailure,
    CollectionRequest,
    CollectionResult,
    NewsSource,
)
from project_g.infrastructure.logging import get_logger
from project_g.ports.http import (
    HttpClient,
    HttpDomainNotAllowedError,
    HttpRedirectLimitError,
    HttpRequestError,
    HttpResponseTooLargeError,
    HttpStatusError,
    HttpTimeoutError,
)

_ARTICLE_PATH_PATTERN = re.compile(r"^/news/(?P<article_id>[0-9]+)/?$")
_DATE_PATTERN = re.compile(
    r"(?P<year>20[0-9]{2})"
    r"[./年-]"
    r"(?P<month>[0-9]{1,2})"
    r"[./月-]"
    r"(?P<day>[0-9]{1,2})日?"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")

JAPAN_TIMEZONE = ZoneInfo("Asia/Tokyo")


class GiantsOfficialNewsParser:
    def parse(
        self,
        html: str,
        *,
        source: NewsSource,
        collected_at: datetime,
        max_items: int,
    ) -> tuple[CollectedNewsItem, ...]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[CollectedNewsItem] = []
        seen_urls: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")

            if not isinstance(href, str):
                continue

            canonical_url = self._canonicalize_url(
                href,
                base_url=source.base_url,
            )

            if canonical_url is None:
                continue

            if canonical_url in seen_urls:
                continue

            match = _ARTICLE_PATH_PATTERN.fullmatch(urlparse(canonical_url).path)

            if match is None:
                continue

            published_at = self._find_published_at(anchor)

            if published_at is None:
                continue

            title = self._extract_title(anchor)

            if not title:
                continue

            seen_urls.add(canonical_url)

            items.append(
                CollectedNewsItem(
                    source_id=source.source_id,
                    source_name=source.name,
                    title=title,
                    source_url=canonical_url,
                    canonical_url=canonical_url,
                    published_at=published_at,
                    collected_at=collected_at,
                    external_id=match.group("article_id"),
                )
            )

            if len(items) >= max_items:
                break

        return tuple(items)

    @staticmethod
    def _canonicalize_url(
        href: str,
        *,
        base_url: str,
    ) -> str | None:
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        host = (parsed.hostname or "").casefold()

        if parsed.scheme != "https" or host not in {"www.giants.jp", "giants.jp"}:
            return None

        if _ARTICLE_PATH_PATTERN.fullmatch(parsed.path) is None:
            return None

        return urlunparse(
            (
                "https",
                "www.giants.jp",
                parsed.path,
                "",
                "",
                "",
            )
        )

    @staticmethod
    def _extract_title(anchor: Tag) -> str:
        text = anchor.get_text(" ", strip=True)
        text = _DATE_PATTERN.sub(" ", text)
        return _WHITESPACE_PATTERN.sub(" ", text).strip()

    @staticmethod
    def _find_published_at(
        anchor: Tag,
    ) -> datetime | None:
        current: Tag | None = anchor

        for _depth in range(5):
            if current is None:
                break

            if current.name in {"html", "body", "main"}:
                break

            text = current.get_text(" ", strip=True)
            match = _DATE_PATTERN.search(text)

            if match is not None:
                try:
                    return datetime(
                        year=int(match.group("year")),
                        month=int(match.group("month")),
                        day=int(match.group("day")),
                        tzinfo=JAPAN_TIMEZONE,
                    )
                except ValueError:
                    return None

            parent = current.parent
            current = parent if isinstance(parent, Tag) else None

        return None


type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GiantsOfficialNewsCollector:
    ALLOWED_HOSTS = frozenset(
        {
            "www.giants.jp",
            "giants.jp",
        }
    )

    def __init__(
        self,
        *,
        source: NewsSource,
        http_client: HttpClient,
        parser: GiantsOfficialNewsParser,
        max_response_bytes: int,
        clock: Clock = _utc_now,
    ) -> None:
        self._source = source
        self._http_client = http_client
        self._parser = parser
        self._max_response_bytes = max_response_bytes
        self._clock = clock
        self._logger = get_logger("project_g.collectors.giants_official_news")

    @property
    def source(self) -> NewsSource:
        return self._source

    def collect(
        self,
        request: CollectionRequest,
    ) -> CollectionResult:
        if request.source.source_id != self._source.source_id:
            raise ValueError("Collection request source does not match the Collector source")

        started_at = self._clock()

        self._logger.info(
            "news_collection_started",
            event_name="news_collection_started",
            source_id=self._source.source_id,
            max_items=request.max_items,
        )

        if not self._source.collectable:
            return self._failed(
                started_at=started_at,
                code="SOURCE_NOT_COLLECTABLE",
                message="The news source is not enabled",
                retryable=False,
            )

        try:
            response = self._http_client.get(
                self._source.base_url,
                timeout_seconds=request.timeout_seconds,
                max_response_bytes=self._max_response_bytes,
                allowed_hosts=self.ALLOWED_HOSTS,
            )

            if "text/html" not in response.content_type:
                return self._failed(
                    started_at=started_at,
                    code="SOURCE_CONTENT_TYPE_INVALID",
                    message="The source did not return HTML",
                    retryable=False,
                )

            collected_at = self._clock()

            items = self._parser.parse(
                response.text,
                source=self._source,
                collected_at=collected_at,
                max_items=request.max_items,
            )

        except HttpTimeoutError:
            return self._failed(
                started_at=started_at,
                code="SOURCE_TIMEOUT",
                message="The source request timed out",
                retryable=True,
            )
        except HttpResponseTooLargeError:
            return self._failed(
                started_at=started_at,
                code="SOURCE_RESPONSE_TOO_LARGE",
                message="The source response exceeded the limit",
                retryable=False,
            )
        except HttpDomainNotAllowedError:
            return self._failed(
                started_at=started_at,
                code="SOURCE_REDIRECT_NOT_ALLOWED",
                message="The source redirected outside the approved domain",
                retryable=False,
            )
        except HttpRedirectLimitError:
            return self._failed(
                started_at=started_at,
                code="SOURCE_REDIRECT_LIMIT",
                message="The source exceeded the redirect limit",
                retryable=True,
            )
        except HttpStatusError as error:
            return self._failed(
                started_at=started_at,
                code="SOURCE_HTTP_STATUS",
                message=(f"The source returned HTTP status {error.status_code}"),
                retryable=error.status_code >= 500,
            )
        except HttpRequestError:
            return self._failed(
                started_at=started_at,
                code="SOURCE_REQUEST_FAILED",
                message="The source request failed",
                retryable=True,
            )

        completed_at = self._clock()

        if not items:
            self._logger.info(
                "news_collection_empty",
                event_name="news_collection_empty",
                source_id=self._source.source_id,
            )

            return CollectionResult.empty(
                source=self._source,
                started_at=started_at,
                completed_at=completed_at,
            )

        self._logger.info(
            "news_collection_completed",
            event_name="news_collection_completed",
            source_id=self._source.source_id,
            item_count=len(items),
        )

        return CollectionResult.succeeded(
            source=self._source,
            items=items,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _failed(
        self,
        *,
        started_at: datetime,
        code: str,
        message: str,
        retryable: bool,
    ) -> CollectionResult:
        completed_at = self._clock()

        self._logger.warning(
            "news_collection_failed",
            event_name="news_collection_failed",
            source_id=self._source.source_id,
            error_code=code,
            retryable=retryable,
        )

        return CollectionResult.failed(
            source=self._source,
            failure=CollectionFailure(
                code=code,
                message=message,
                retryable=retryable,
            ),
            started_at=started_at,
            completed_at=completed_at,
        )
