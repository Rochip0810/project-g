from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from project_g.application.news.complete_metadata_enrichment import (
    CompleteExtractedNewsMetadataEnrichment,
    CompleteUnavailableNewsMetadataEnrichment,
    FailNewsMetadataEnrichment,
    NewsMetadataEnrichmentResult,
)
from project_g.ports.http import (
    HttpClient,
    HttpClientError,
    HttpStatusError,
)
from project_g.ports.news_metadata import (
    NewsMetadataExtractionError,
    NewsMetadataParser,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataRepository,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobRepository,
)

Clock = Callable[[], datetime]

_UNAVAILABLE_HTTP_STATUSES = frozenset(
    {
        401,
        403,
        404,
        410,
    }
)

_ALLOWED_HTML_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AutoEnrichNewsArticleMetadata:
    def __init__(
        self,
        *,
        http_client: HttpClient,
        parser: NewsMetadataParser,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        timeout_seconds: float,
        max_response_bytes: int,
        clock: Clock = _utc_now,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")

        self._http_client = http_client
        self._parser = parser
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

        self._complete_extracted = CompleteExtractedNewsMetadataEnrichment(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )
        self._complete_unavailable = CompleteUnavailableNewsMetadataEnrichment(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )
        self._fail = FailNewsMetadataEnrichment(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )

    def execute(
        self,
        *,
        intake_id: UUID,
        url: str,
        allowed_hosts: frozenset[str],
    ) -> NewsMetadataEnrichmentResult:
        try:
            response = self._http_client.get(
                url,
                timeout_seconds=self._timeout_seconds,
                max_response_bytes=self._max_response_bytes,
                allowed_hosts=allowed_hosts,
            )
        except HttpStatusError as error:
            if error.status_code in _UNAVAILABLE_HTTP_STATUSES:
                return self._complete_unavailable.execute(
                    intake_id=intake_id,
                    reason=(f"Automatic metadata extraction unavailable: HTTP {error.status_code}"),
                )

            return self._fail.execute(
                intake_id=intake_id,
                reason=(f"Automatic metadata request failed: HTTP {error.status_code}"),
            )
        except HttpClientError as error:
            return self._fail.execute(
                intake_id=intake_id,
                reason=(f"Automatic metadata request failed: {type(error).__name__}"),
            )

        if not any(
            content_type in response.content_type for content_type in _ALLOWED_HTML_CONTENT_TYPES
        ):
            return self._fail.execute(
                intake_id=intake_id,
                reason=("Automatic metadata extraction requires an HTML response"),
            )

        try:
            extracted = self._parser.parse(response.text)
        except NewsMetadataExtractionError as error:
            return self._fail.execute(
                intake_id=intake_id,
                reason=(f"Automatic metadata parsing failed: {error}"),
            )

        return self._complete_extracted.execute(
            intake_id=intake_id,
            title=extracted.title,
            published_at=extracted.published_at,
            description=extracted.description,
        )
