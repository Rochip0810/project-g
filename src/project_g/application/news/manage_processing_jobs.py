from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobNotFoundError,
    NewsProcessingJobRepository,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StartOldestNewsProcessingJob:
    def __init__(
        self,
        *,
        repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self) -> NewsProcessingJob | None:
        pending_job = self._repository.get_oldest_pending()

        if pending_job is None:
            return None

        processing_job = pending_job.start(
            started_at=self._clock(),
        )

        return self._repository.update(processing_job)


class CompleteNewsProcessingJob:
    def __init__(
        self,
        *,
        repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob:
        job = self._get_job(job_id)

        completed_job = job.complete(
            completed_at=self._clock(),
        )

        return self._repository.update(completed_job)

    def _get_job(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob:
        job = self._repository.get_by_job_id(job_id)

        if job is None:
            raise NewsProcessingJobNotFoundError(job_id)

        return job


class FailNewsProcessingJob:
    def __init__(
        self,
        *,
        repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        job_id: UUID,
        error: str,
    ) -> NewsProcessingJob:
        job = self._get_job(job_id)

        failed_job = job.fail(
            error=error,
            completed_at=self._clock(),
        )

        return self._repository.update(failed_job)

    def _get_job(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob:
        job = self._repository.get_by_job_id(job_id)

        if job is None:
            raise NewsProcessingJobNotFoundError(job_id)

        return job
