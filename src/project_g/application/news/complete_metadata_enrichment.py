from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.domain.news.processing_job import (
    InvalidNewsProcessingTransitionError,
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataRepository,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobRepository,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsMetadataEnrichmentTargetNotFoundError(RuntimeError):
    """Raised when enrichment records cannot be found."""

    def __init__(
        self,
        *,
        intake_id: UUID,
        target: str,
    ) -> None:
        super().__init__(f"{target} was not found for intake: {intake_id}")
        self.intake_id = intake_id
        self.target = target


@dataclass(frozen=True, slots=True)
class NewsMetadataEnrichmentResult:
    metadata: NewsArticleMetadata
    processing_job: NewsProcessingJob


class _NewsMetadataEnrichmentService:
    def __init__(
        self,
        *,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        clock: Clock,
    ) -> None:
        self._metadata_repository = metadata_repository
        self._job_repository = job_repository
        self._clock = clock

    def _load_records(
        self,
        intake_id: UUID,
    ) -> tuple[NewsArticleMetadata, NewsProcessingJob]:
        metadata = self._metadata_repository.get_by_intake_id(intake_id)

        if metadata is None:
            raise NewsMetadataEnrichmentTargetNotFoundError(
                intake_id=intake_id,
                target="Article metadata",
            )

        job = self._job_repository.get_by_intake_id(intake_id)

        if job is None:
            raise NewsMetadataEnrichmentTargetNotFoundError(
                intake_id=intake_id,
                target="Processing job",
            )

        return metadata, job

    @staticmethod
    def _start_if_pending(
        job: NewsProcessingJob,
        *,
        changed_at: datetime,
    ) -> NewsProcessingJob:
        if job.status is NewsProcessingStatus.PENDING:
            return job.start(
                started_at=changed_at,
            )

        if job.status is NewsProcessingStatus.PROCESSING:
            return job

        raise InvalidNewsProcessingTransitionError(
            "Metadata enrichment requires a pending or processing job"
        )

    def _store_completed(
        self,
        *,
        metadata: NewsArticleMetadata,
        job: NewsProcessingJob,
        changed_at: datetime,
    ) -> NewsMetadataEnrichmentResult:
        stored_metadata = self._metadata_repository.update(metadata)
        stored_job = self._job_repository.update(
            job.complete(
                completed_at=changed_at,
            )
        )

        return NewsMetadataEnrichmentResult(
            metadata=stored_metadata,
            processing_job=stored_job,
        )

    def _store_failed(
        self,
        *,
        metadata: NewsArticleMetadata,
        job: NewsProcessingJob,
        reason: str,
        changed_at: datetime,
    ) -> NewsMetadataEnrichmentResult:
        stored_metadata = self._metadata_repository.update(metadata)
        stored_job = self._job_repository.update(
            job.fail(
                error=reason,
                completed_at=changed_at,
            )
        )

        return NewsMetadataEnrichmentResult(
            metadata=stored_metadata,
            processing_job=stored_job,
        )


class CompleteManualNewsMetadataEnrichment(_NewsMetadataEnrichmentService):
    def __init__(
        self,
        *,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        super().__init__(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )

    def execute(
        self,
        *,
        intake_id: UUID,
        title: str,
        published_at: datetime | None,
        description: str | None,
    ) -> NewsMetadataEnrichmentResult:
        changed_at = self._clock()
        metadata, job = self._load_records(intake_id)

        updated_metadata = metadata.record_manual(
            title=title,
            published_at=published_at,
            description=description,
            updated_at=changed_at,
        )

        if metadata.status is NewsMetadataStatus.UNAVAILABLE:
            if job.status is not NewsProcessingStatus.COMPLETED:
                raise InvalidNewsProcessingTransitionError(
                    "Unavailable metadata requires a completed job"
                )

            stored_metadata = self._metadata_repository.update(updated_metadata)

            return NewsMetadataEnrichmentResult(
                metadata=stored_metadata,
                processing_job=job,
            )

        processing_job = self._start_if_pending(
            job,
            changed_at=changed_at,
        )

        return self._store_completed(
            metadata=updated_metadata,
            job=processing_job,
            changed_at=changed_at,
        )


class CompleteExtractedNewsMetadataEnrichment(_NewsMetadataEnrichmentService):
    def __init__(
        self,
        *,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        super().__init__(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )

    def execute(
        self,
        *,
        intake_id: UUID,
        title: str,
        published_at: datetime | None,
        description: str | None,
    ) -> NewsMetadataEnrichmentResult:
        changed_at = self._clock()
        metadata, job = self._load_records(intake_id)
        processing_job = self._start_if_pending(
            job,
            changed_at=changed_at,
        )

        updated_metadata = metadata.record_extracted(
            title=title,
            published_at=published_at,
            description=description,
            updated_at=changed_at,
        )

        return self._store_completed(
            metadata=updated_metadata,
            job=processing_job,
            changed_at=changed_at,
        )


class CompleteUnavailableNewsMetadataEnrichment(_NewsMetadataEnrichmentService):
    def __init__(
        self,
        *,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        super().__init__(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )

    def execute(
        self,
        *,
        intake_id: UUID,
        reason: str,
    ) -> NewsMetadataEnrichmentResult:
        changed_at = self._clock()
        metadata, job = self._load_records(intake_id)
        processing_job = self._start_if_pending(
            job,
            changed_at=changed_at,
        )

        updated_metadata = metadata.mark_unavailable(
            reason=reason,
            updated_at=changed_at,
        )

        return self._store_completed(
            metadata=updated_metadata,
            job=processing_job,
            changed_at=changed_at,
        )


class FailNewsMetadataEnrichment(_NewsMetadataEnrichmentService):
    def __init__(
        self,
        *,
        metadata_repository: NewsArticleMetadataRepository,
        job_repository: NewsProcessingJobRepository,
        clock: Clock = _utc_now,
    ) -> None:
        super().__init__(
            metadata_repository=metadata_repository,
            job_repository=job_repository,
            clock=clock,
        )

    def execute(
        self,
        *,
        intake_id: UUID,
        reason: str,
    ) -> NewsMetadataEnrichmentResult:
        changed_at = self._clock()
        metadata, job = self._load_records(intake_id)
        processing_job = self._start_if_pending(
            job,
            changed_at=changed_at,
        )

        updated_metadata = metadata.mark_failed(
            reason=reason,
            updated_at=changed_at,
        )

        return self._store_failed(
            metadata=updated_metadata,
            job=processing_job,
            reason=reason,
            changed_at=changed_at,
        )
