from typing import Protocol
from uuid import UUID

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)


class NewsProcessingJobAlreadyExistsError(RuntimeError):
    """Raised when an intake already has a processing job."""

    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Processing job already exists for intake: {intake_id}")
        self.intake_id = intake_id


class NewsProcessingJobNotFoundError(RuntimeError):
    """Raised when a processing job cannot be found."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"Processing job was not found: {job_id}")
        self.job_id = job_id


class NewsProcessingJobRepository(Protocol):
    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        """Store and return a new processing job."""
        ...

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        """Update and return an existing processing job."""
        ...

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        """Return a processing job by its ID."""
        ...

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        """Return the processing job associated with an intake."""
        ...

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        """Return the oldest pending job."""
        ...
