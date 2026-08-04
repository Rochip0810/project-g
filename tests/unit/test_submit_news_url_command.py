from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import pytest

from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.interfaces.management.submit_news_url import (
    SubmittedNewsUrl,
    parse_arguments,
    print_submission,
)

_INTAKE_ID = UUID("19e78508-577e-44ea-a304-7d5ee9d0716d")
_JOB_ID = UUID("4cb52bb6-3e98-48aa-a3ae-607f2d06391c")
_SUBMITTED_AT = datetime(
    2026,
    8,
    4,
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

    return SubmittedNewsUrl(
        intake=intake,
        processing_job=job,
    )


def test_parse_arguments_accepts_url() -> None:
    arguments = parse_arguments(["https://www.giants.jp/news/12345/"])

    assert arguments.url == ("https://www.giants.jp/news/12345/")


def test_parse_arguments_requires_url() -> None:
    with pytest.raises(SystemExit):
        parse_arguments([])


def test_print_submission_displays_intake_and_job() -> None:
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
