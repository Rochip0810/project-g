from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobAlreadyExistsError,
    NewsProcessingJobRepository,
)

Clock = Callable[[], datetime]
JobIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateNewsProcessingJob:
    def __init__(
        self,
        *,
        repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
        job_id_factory: JobIdFactory = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._job_id_factory = job_id_factory

    def execute(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob:
        existing = self._repository.get_by_intake_id(intake_id)

        if existing is not None:
            raise NewsProcessingJobAlreadyExistsError(intake_id)

        job = NewsProcessingJob.pending(
            job_id=self._job_id_factory(),
            intake_id=intake_id,
            created_at=self._clock(),
        )

        return self._repository.add(job)
