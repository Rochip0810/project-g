from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.manage_processing_jobs import (
    CompleteNewsProcessingJob,
    FailNewsProcessingJob,
    StartOldestNewsProcessingJob,
)
from project_g.domain.news.processing_job import (
    InvalidNewsProcessingTransitionError,
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobAlreadyExistsError,
    NewsProcessingJobNotFoundError,
)

_JOB_1_ID = UUID("31b395fa-87d4-474d-a42b-bcb0cd20145a")
_JOB_2_ID = UUID("2ba053bb-63d3-46a7-aa4e-825ce6e74575")
_UNKNOWN_JOB_ID = UUID("69ed8d17-4669-448a-9943-3df391269308")

_INTAKE_1_ID = UUID("46b89829-1ab8-413c-b121-7be59f425483")
_INTAKE_2_ID = UUID("315e1020-3a60-4be0-8ae7-d4b19f19c078")

_CREATED_AT = datetime(2026, 8, 4, 13, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)


class FakeNewsProcessingJobRepository:
    def __init__(self) -> None:
        self._by_job_id: dict[UUID, NewsProcessingJob] = {}
        self._by_intake_id: dict[UUID, NewsProcessingJob] = {}

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        if job.intake_id in self._by_intake_id:
            raise NewsProcessingJobAlreadyExistsError(job.intake_id)

        self._by_job_id[job.job_id] = job
        self._by_intake_id[job.intake_id] = job

        return job

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        if job.job_id not in self._by_job_id:
            raise NewsProcessingJobNotFoundError(job.job_id)

        self._by_job_id[job.job_id] = job
        self._by_intake_id[job.intake_id] = job

        return job

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        return self._by_job_id.get(job_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        return self._by_intake_id.get(intake_id)

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        pending_jobs = [
            job for job in self._by_job_id.values() if job.status is NewsProcessingStatus.PENDING
        ]

        if not pending_jobs:
            return None

        return min(
            pending_jobs,
            key=lambda job: (
                job.created_at,
                str(job.job_id),
            ),
        )


def _pending(
    *,
    job_id: UUID = _JOB_1_ID,
    intake_id: UUID = _INTAKE_1_ID,
    created_at: datetime = _CREATED_AT,
) -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=job_id,
        intake_id=intake_id,
        created_at=created_at,
    )


def test_start_service_starts_oldest_pending_job() -> None:
    repository = FakeNewsProcessingJobRepository()

    newer = _pending(
        job_id=_JOB_2_ID,
        intake_id=_INTAKE_2_ID,
        created_at=_CREATED_AT + timedelta(minutes=1),
    )
    older = _pending()

    repository.add(newer)
    repository.add(older)

    started = StartOldestNewsProcessingJob(
        repository=repository,
        clock=lambda: _STARTED_AT,
    ).execute()

    assert started is not None
    assert started.job_id == older.job_id
    assert started.status is NewsProcessingStatus.PROCESSING
    assert started.attempt_count == 1
    assert started.started_at == _STARTED_AT


def test_start_service_returns_none_without_pending_job() -> None:
    repository = FakeNewsProcessingJobRepository()

    started = StartOldestNewsProcessingJob(
        repository=repository,
        clock=lambda: _STARTED_AT,
    ).execute()

    assert started is None


def test_complete_service_completes_processing_job() -> None:
    repository = FakeNewsProcessingJobRepository()
    processing = _pending().start(started_at=_STARTED_AT)
    repository.add(processing)

    completed = CompleteNewsProcessingJob(
        repository=repository,
        clock=lambda: _COMPLETED_AT,
    ).execute(processing.job_id)

    assert completed.status is NewsProcessingStatus.COMPLETED
    assert completed.completed_at == _COMPLETED_AT
    assert completed.last_error is None


def test_fail_service_fails_processing_job() -> None:
    repository = FakeNewsProcessingJobRepository()
    processing = _pending().start(started_at=_STARTED_AT)
    repository.add(processing)

    failed = FailNewsProcessingJob(
        repository=repository,
        clock=lambda: _COMPLETED_AT,
    ).execute(
        job_id=processing.job_id,
        error="  article processing failed  ",
    )

    assert failed.status is NewsProcessingStatus.FAILED
    assert failed.last_error == "article processing failed"
    assert failed.completed_at == _COMPLETED_AT


def test_complete_service_rejects_unknown_job() -> None:
    repository = FakeNewsProcessingJobRepository()

    with pytest.raises(NewsProcessingJobNotFoundError):
        CompleteNewsProcessingJob(
            repository=repository,
            clock=lambda: _COMPLETED_AT,
        ).execute(_UNKNOWN_JOB_ID)


def test_complete_service_rejects_pending_job() -> None:
    repository = FakeNewsProcessingJobRepository()
    pending = _pending()
    repository.add(pending)

    with pytest.raises(
        InvalidNewsProcessingTransitionError,
        match="Cannot complete",
    ):
        CompleteNewsProcessingJob(
            repository=repository,
            clock=lambda: _COMPLETED_AT,
        ).execute(pending.job_id)
