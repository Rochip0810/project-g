from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.processing_job import (
    InvalidNewsProcessingJobError,
    InvalidNewsProcessingTransitionError,
    NewsProcessingJob,
    NewsProcessingStatus,
)

_JOB_ID = UUID("a34728ce-682a-44ee-b49f-a3c677657354")
_INTAKE_ID = UUID("2458e63d-ee76-47c1-bde6-42d62ad8af64")
_CREATED_AT = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)


def _pending() -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _processing() -> NewsProcessingJob:
    return _pending().start(
        started_at=_STARTED_AT,
    )


def test_pending_factory_creates_unstarted_job() -> None:
    job = _pending()

    assert job.status is NewsProcessingStatus.PENDING
    assert job.attempt_count == 0
    assert job.last_error is None
    assert job.started_at is None
    assert job.completed_at is None
    assert job.updated_at == _CREATED_AT


def test_pending_job_can_start() -> None:
    job = _processing()

    assert job.status is NewsProcessingStatus.PROCESSING
    assert job.attempt_count == 1
    assert job.started_at == _STARTED_AT
    assert job.updated_at == _STARTED_AT


def test_processing_job_can_complete() -> None:
    job = _processing().complete(
        completed_at=_COMPLETED_AT,
    )

    assert job.status is NewsProcessingStatus.COMPLETED
    assert job.completed_at == _COMPLETED_AT
    assert job.last_error is None
    assert job.updated_at == _COMPLETED_AT


def test_processing_job_can_fail() -> None:
    job = _processing().fail(
        error="  article processing failed  ",
        completed_at=_COMPLETED_AT,
    )

    assert job.status is NewsProcessingStatus.FAILED
    assert job.last_error == "article processing failed"
    assert job.completed_at == _COMPLETED_AT


def test_pending_job_cannot_complete() -> None:
    with pytest.raises(
        InvalidNewsProcessingTransitionError,
        match="Cannot complete",
    ):
        _pending().complete(
            completed_at=_COMPLETED_AT,
        )


def test_pending_job_cannot_fail() -> None:
    with pytest.raises(
        InvalidNewsProcessingTransitionError,
        match="Cannot fail",
    ):
        _pending().fail(
            error="failed",
            completed_at=_COMPLETED_AT,
        )


def test_completed_job_cannot_start_again() -> None:
    completed = _processing().complete(
        completed_at=_COMPLETED_AT,
    )

    with pytest.raises(
        InvalidNewsProcessingTransitionError,
        match="Cannot start",
    ):
        completed.start(
            started_at=_COMPLETED_AT + timedelta(minutes=1),
        )


def test_fail_rejects_blank_error() -> None:
    with pytest.raises(
        InvalidNewsProcessingJobError,
        match="error must not be empty",
    ):
        _processing().fail(
            error="   ",
            completed_at=_COMPLETED_AT,
        )


def test_pending_factory_rejects_naive_datetime() -> None:
    with pytest.raises(
        InvalidNewsProcessingJobError,
        match="created_at must be timezone-aware",
    ):
        NewsProcessingJob.pending(
            job_id=_JOB_ID,
            intake_id=_INTAKE_ID,
            created_at=datetime(2026, 8, 4, 10, 0),
        )


def test_job_rejects_completed_at_before_started_at() -> None:
    with pytest.raises(
        InvalidNewsProcessingJobError,
        match="completed_at must not be earlier",
    ):
        _processing().complete(
            completed_at=_CREATED_AT,
        )
