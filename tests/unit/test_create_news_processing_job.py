from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.create_processing_job import (
    CreateNewsProcessingJob,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobAlreadyExistsError,
    NewsProcessingJobNotFoundError,
)

_JOB_ID = UUID("bf863320-d9b9-43bb-ad29-5da3f085fa60")
_INTAKE_ID = UUID("5f4d678b-b51d-4839-a534-afd3f116a294")
_CREATED_AT = datetime(2026, 8, 4, 11, 0, tzinfo=UTC)


class FakeNewsProcessingJobRepository:
    def __init__(self) -> None:
        self._by_job_id: dict[UUID, NewsProcessingJob] = {}
        self._by_intake_id: dict[UUID, NewsProcessingJob] = {}
        self.added: list[NewsProcessingJob] = []

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        if job.intake_id in self._by_intake_id:
            raise NewsProcessingJobAlreadyExistsError(job.intake_id)

        self._by_job_id[job.job_id] = job
        self._by_intake_id[job.intake_id] = job
        self.added.append(job)

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
        pending = [
            job for job in self._by_job_id.values() if job.status is NewsProcessingStatus.PENDING
        ]

        if not pending:
            return None

        return min(
            pending,
            key=lambda job: (
                job.created_at,
                str(job.job_id),
            ),
        )


def _service(
    repository: FakeNewsProcessingJobRepository,
) -> CreateNewsProcessingJob:
    return CreateNewsProcessingJob(
        repository=repository,
        clock=lambda: _CREATED_AT,
        job_id_factory=lambda: _JOB_ID,
    )


def test_service_creates_pending_job() -> None:
    repository = FakeNewsProcessingJobRepository()

    job = _service(repository).execute(_INTAKE_ID)

    assert job.job_id == _JOB_ID
    assert job.intake_id == _INTAKE_ID
    assert job.status is NewsProcessingStatus.PENDING
    assert job.attempt_count == 0
    assert job.created_at == _CREATED_AT
    assert repository.added == [job]


def test_service_rejects_duplicate_intake_job() -> None:
    repository = FakeNewsProcessingJobRepository()
    service = _service(repository)

    first = service.execute(_INTAKE_ID)

    with pytest.raises(
        NewsProcessingJobAlreadyExistsError,
        match="already exists",
    ):
        service.execute(_INTAKE_ID)

    assert repository.added == [first]


def test_repository_returns_oldest_pending_job() -> None:
    repository = FakeNewsProcessingJobRepository()
    service = _service(repository)

    created = service.execute(_INTAKE_ID)

    assert repository.get_oldest_pending() == created
