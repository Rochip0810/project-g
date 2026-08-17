from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import pytest

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)
from project_g.interfaces.management.submit_news_url import (
    SubmittedNewsUrl,
    parse_arguments,
    print_submission,
)

_INTAKE_ID = UUID("19e78508-577e-44ea-a304-7d5ee9d0716d")
_JOB_ID = UUID("4cb52bb6-3e98-48aa-a3ae-607f2d06391c")
_METADATA_ID = UUID("9d02a8c9-f840-44a8-a660-987cc429bd77")
_ANALYSIS_ID = UUID("2753ca42-a173-4dfc-8572-e65b3df259bd")
_SUBMITTED_AT = datetime(
    2026,
    8,
    5,
    12,
    30,
    tzinfo=UTC,
)


def _submission() -> SubmittedNewsUrl:
    intake = ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/12345/?utm_source=google"),
        canonical_url="https://www.giants.jp/news/12345/",
        submitted_at=_SUBMITTED_AT,
    )
    job = NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_SUBMITTED_AT,
    )
    metadata = NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_SUBMITTED_AT,
    )
    relevance = NewsRelevanceAnalysis.pending(
        analysis_id=_ANALYSIS_ID,
        intake_id=_INTAKE_ID,
        created_at=_SUBMITTED_AT,
    )

    return SubmittedNewsUrl(
        intake=intake,
        processing_job=job,
        article_metadata=metadata,
        relevance_analysis=relevance,
    )


def test_parse_arguments_accepts_url() -> None:
    arguments = parse_arguments(["https://www.giants.jp/news/12345/"])

    assert arguments.url == ("https://www.giants.jp/news/12345/")


def test_parse_arguments_requires_url() -> None:
    with pytest.raises(SystemExit):
        parse_arguments([])


def test_print_submission_displays_all_records() -> None:
    output = StringIO()

    print_submission(
        _submission(),
        output=output,
    )

    text = output.getvalue()

    assert "status=created" in text
    assert f"intake_id={_INTAKE_ID}" in text
    assert "source_id=giants_official_news" in text
    assert "canonical_url=https://www.giants.jp/news/12345/" in text
    assert f"processing_job_id={_JOB_ID}" in text
    assert "processing_status=pending" in text
    assert "processing_attempt_count=0" in text
    assert f"article_metadata_id={_METADATA_ID}" in text
    assert "article_metadata_status=pending" in text
    assert f"relevance_analysis_id={_ANALYSIS_ID}" in text
    assert "relevance_analysis_status=pending" in text


def test_submission_is_enqueued_after_creation() -> None:
    from collections.abc import Mapping, Sequence

    from project_g.interfaces.management.submit_news_url import (
        enqueue_submission,
    )
    from project_g.ports.queue import (
        JobArgument,
        JobSnapshot,
        QueueName,
    )

    class FakeQueueProvider:
        def __init__(self) -> None:
            self.function_path: str | None = None
            self.args: Sequence[JobArgument] = ()

        def enqueue(
            self,
            queue_name: QueueName,
            function_path: str,
            *,
            args: Sequence[JobArgument] = (),
            kwargs: Mapping[str, JobArgument] | None = None,
            job_id: str | None = None,
            description: str | None = None,
        ) -> JobSnapshot:
            self.function_path = function_path
            self.args = args

            return JobSnapshot(
                job_id=job_id or "generated",
                queue=queue_name,
                status="queued",
            )

    provider = FakeQueueProvider()
    submission = _submission()

    snapshot = enqueue_submission(
        queue_provider=provider,
        submission=submission,
    )

    assert provider.function_path == ("project_g.interfaces.workers.jobs.process_news_metadata")
    assert provider.args == [str(_INTAKE_ID)]
    assert snapshot.queue is QueueName.DEFAULT
    assert snapshot.status == "queued"


def test_print_queue_result_displays_queue_state() -> None:
    from project_g.interfaces.management.submit_news_url import (
        print_queue_result,
    )
    from project_g.ports.queue import (
        JobSnapshot,
        QueueName,
    )

    output = StringIO()

    print_queue_result(
        JobSnapshot(
            job_id="news-metadata-test",
            queue=QueueName.DEFAULT,
            status="queued",
        ),
        output=output,
    )

    text = output.getvalue()

    assert "queue_job_id=news-metadata-test" in text
    assert "queue_name=default" in text
    assert "queue_status=queued" in text
