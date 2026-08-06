from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.auto_enrich_article_metadata import (
    AutoEnrichNewsArticleMetadata,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.infrastructure.news_metadata import (
    SafeHtmlNewsMetadataParser,
)
from project_g.ports.http import (
    HttpClientError,
    HttpResponse,
    HttpStatusError,
    HttpTimeoutError,
)

_INTAKE_ID = UUID("1d13c8fd-fd31-44d6-a613-2ca8de0dfecd")
_METADATA_ID = UUID("6768797f-5f91-41c8-9718-b90e1425842b")
_JOB_ID = UUID("7584057b-359f-4104-9492-414752ae53cc")

_URL = "https://www.giants.jp/news/123456/"
_ALLOWED_HOSTS = frozenset(
    {
        "www.giants.jp",
        "giants.jp",
    }
)

_CREATED_AT = datetime(
    2026,
    8,
    5,
    12,
    0,
    tzinfo=UTC,
)
_COMPLETED_AT = _CREATED_AT + timedelta(minutes=1)
_PUBLISHED_AT = datetime(
    2026,
    8,
    5,
    9,
    0,
    tzinfo=UTC,
)


class StubHttpClient:
    def __init__(
        self,
        *,
        response: HttpResponse | None = None,
        error: HttpClientError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, float, int, frozenset[str]]] = []

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        self.calls.append(
            (
                url,
                timeout_seconds,
                max_response_bytes,
                allowed_hosts,
            )
        )

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("Stub response was not configured")

        return self.response


class FakeMetadataRepository:
    def __init__(self) -> None:
        self.metadata = NewsArticleMetadata.pending(
            metadata_id=_METADATA_ID,
            intake_id=_INTAKE_ID,
            created_at=_CREATED_AT,
        )

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.metadata = metadata
        return metadata

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.metadata = metadata
        return metadata

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        if self.metadata.metadata_id == metadata_id:
            return self.metadata

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        if self.metadata.intake_id == intake_id:
            return self.metadata

        return None


class FakeJobRepository:
    def __init__(self) -> None:
        self.job = NewsProcessingJob.pending(
            job_id=_JOB_ID,
            intake_id=_INTAKE_ID,
            created_at=_CREATED_AT,
        )

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.job = job
        return job

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.job = job
        return job

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        if self.job.job_id == job_id:
            return self.job

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        if self.job.intake_id == intake_id:
            return self.job

        return None

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        if self.job.status is NewsProcessingStatus.PENDING:
            return self.job

        return None


def _html_response(
    html: str,
    *,
    content_type: str = "text/html; charset=utf-8",
) -> HttpResponse:
    return HttpResponse(
        requested_url=_URL,
        final_url=_URL,
        status_code=200,
        headers={
            "content-type": content_type,
        },
        body=html.encode(),
    )


def _service(
    http_client: StubHttpClient,
) -> tuple[
    AutoEnrichNewsArticleMetadata,
    FakeMetadataRepository,
    FakeJobRepository,
]:
    metadata_repository = FakeMetadataRepository()
    job_repository = FakeJobRepository()

    service = AutoEnrichNewsArticleMetadata(
        http_client=http_client,
        parser=SafeHtmlNewsMetadataParser(),
        metadata_repository=metadata_repository,
        job_repository=job_repository,
        timeout_seconds=10.0,
        max_response_bytes=1_000_000,
        clock=lambda: _COMPLETED_AT,
    )

    return (
        service,
        metadata_repository,
        job_repository,
    )


def test_successful_html_is_recorded_as_extracted() -> None:
    client = StubHttpClient(
        response=_html_response(
            """
            <html>
              <head>
                <meta
                  property="og:title"
                  content="Giants roster announcement"
                >
                <meta
                  property="og:description"
                  content="Official announcement."
                >
                <meta
                  property="article:published_time"
                  content="2026-08-05T18:00:00+09:00"
                >
              </head>
            </html>
            """
        )
    )
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.EXTRACTED
    assert result.metadata.title == ("Giants roster announcement")
    assert result.metadata.published_at == _PUBLISHED_AT
    assert result.processing_job.status is NewsProcessingStatus.COMPLETED
    assert client.calls == [
        (
            _URL,
            10.0,
            1_000_000,
            _ALLOWED_HOSTS,
        )
    ]


@pytest.mark.parametrize(
    "status_code",
    [
        401,
        403,
        404,
        410,
    ],
)
def test_unavailable_http_status_is_recorded(
    status_code: int,
) -> None:
    client = StubHttpClient(
        error=HttpStatusError(
            status_code,
            _URL,
        )
    )
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.UNAVAILABLE
    assert result.metadata.failure_reason == (
        f"Automatic metadata extraction unavailable: HTTP {status_code}"
    )
    assert result.processing_job.status is NewsProcessingStatus.COMPLETED


def test_server_error_is_recorded_as_failed() -> None:
    client = StubHttpClient(
        error=HttpStatusError(
            503,
            _URL,
        )
    )
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.FAILED
    assert result.processing_job.status is NewsProcessingStatus.FAILED
    assert result.metadata.failure_reason == ("Automatic metadata request failed: HTTP 503")


def test_timeout_is_recorded_as_failed() -> None:
    client = StubHttpClient(error=HttpTimeoutError("HTTP request timed out"))
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.FAILED
    assert result.metadata.failure_reason == ("Automatic metadata request failed: HttpTimeoutError")


def test_non_html_response_is_recorded_as_failed() -> None:
    client = StubHttpClient(
        response=_html_response(
            "{}",
            content_type="application/json",
        )
    )
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.FAILED
    assert result.metadata.failure_reason == (
        "Automatic metadata extraction requires an HTML response"
    )


def test_parser_failure_is_recorded_as_failed() -> None:
    client = StubHttpClient(
        response=_html_response(
            """
            <html>
              <head>
                <meta
                  name="description"
                  content="No title exists."
                >
              </head>
            </html>
            """
        )
    )
    service, _, _ = _service(client)

    result = service.execute(
        intake_id=_INTAKE_ID,
        url=_URL,
        allowed_hosts=_ALLOWED_HOSTS,
    )

    assert result.metadata.status is NewsMetadataStatus.FAILED
    assert result.metadata.failure_reason == (
        "Automatic metadata parsing failed: Article title was not found"
    )
