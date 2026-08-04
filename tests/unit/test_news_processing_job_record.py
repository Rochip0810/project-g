from datetime import UTC, datetime, timedelta
from uuid import UUID

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.infrastructure.database.base import Base
from project_g.infrastructure.database.models.news_processing_job import (
    NewsProcessingJobRecord,
)

_JOB_ID = UUID("36567f59-2631-4dca-a3aa-723cb23a8676")
_INTAKE_ID = UUID("e3063963-1dc0-4fd7-8173-c6c732d977a2")
_CREATED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)


def _pending() -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_news_processing_jobs_table_is_registered() -> None:
    assert "news_processing_jobs" in Base.metadata.tables


def test_pending_job_record_round_trip() -> None:
    job = _pending()

    record = NewsProcessingJobRecord.from_domain(job)

    assert record.job_id == job.job_id
    assert record.intake_id == job.intake_id
    assert record.status == "pending"
    assert record.to_domain() == job


def test_failed_job_record_round_trip() -> None:
    job = (
        _pending()
        .start(started_at=_STARTED_AT)
        .fail(
            error="processing failed",
            completed_at=_COMPLETED_AT,
        )
    )

    record = NewsProcessingJobRecord.from_domain(job)

    assert record.status == "failed"
    assert record.last_error == "processing failed"
    assert record.to_domain() == job
