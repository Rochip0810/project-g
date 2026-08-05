from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.complete_metadata_enrichment import (
    CompleteExtractedNewsMetadataEnrichment,
    CompleteManualNewsMetadataEnrichment,
    CompleteUnavailableNewsMetadataEnrichment,
    FailNewsMetadataEnrichment,
    NewsMetadataEnrichmentTargetNotFoundError,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)

_METADATA_ID = UUID("751ac0e1-b9c3-4473-b1c3-20c5cd649d91")
_JOB_ID = UUID("2be0748c-1265-463c-a698-ff4eb36568da")
_INTAKE_ID = UUID("4826267f-bbbb-4fc3-9f64-47670b0fd552")

_CREATED_AT = datetime(
    2026,
    8,
    5,
    18,
    0,
    tzinfo=UTC,
)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)
_PUBLISHED_AT = datetime(
    2026,
    8,
    5,
    12,
    0,
    tzinfo=UTC,
)


class FakeMetadataRepository:
    def __init__(
        self,
        metadata: NewsArticleMetadata | None,
    ) -> None:
        self.metadata = metadata
        self.updated: list[NewsArticleMetadata] = []

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.metadata = metadata
        return metadata

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.metadata = metadata
        self.updated.append(metadata)
        return metadata

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        if self.metadata is not None and self.metadata.metadata_id == metadata_id:
            return self.metadata

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        if self.metadata is not None and self.metadata.intake_id == intake_id:
            return self.metadata

        return None


class FakeJobRepository:
    def __init__(
        self,
        job: NewsProcessingJob | None,
    ) -> None:
        self.job = job
        self.updated: list[NewsProcessingJob] = []

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.job = job
        return job

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.job = job
        self.updated.append(job)
        return job

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        if self.job is not None and self.job.job_id == job_id:
            return self.job

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        if self.job is not None and self.job.intake_id == intake_id:
            return self.job

        return None

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        if self.job is not None and self.job.status is NewsProcessingStatus.PENDING:
            return self.job

        return None


def _pending_metadata() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _pending_job() -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_manual_enrichment_completes_metadata_and_job() -> None:
    metadata_repository = FakeMetadataRepository(_pending_metadata())
    job_repository = FakeJobRepository(_pending_job())

    result = CompleteManualNewsMetadataEnrichment(
        metadata_repository=metadata_repository,
        job_repository=job_repository,
        clock=lambda: _COMPLETED_AT,
    ).execute(
        intake_id=_INTAKE_ID,
        title="Manual Giants title",
        published_at=_PUBLISHED_AT,
        description="Manually entered description.",
    )

    assert result.metadata.status is NewsMetadataStatus.MANUAL
    assert result.metadata.title == "Manual Giants title"
    assert result.processing_job.status is NewsProcessingStatus.COMPLETED
    assert result.processing_job.attempt_count == 1
    assert result.processing_job.started_at == _COMPLETED_AT
    assert result.processing_job.completed_at == _COMPLETED_AT


def test_extracted_enrichment_completes_processing_job() -> None:
    processing = _pending_job().start(started_at=_STARTED_AT)

    result = CompleteExtractedNewsMetadataEnrichment(
        metadata_repository=FakeMetadataRepository(_pending_metadata()),
        job_repository=FakeJobRepository(processing),
        clock=lambda: _COMPLETED_AT,
    ).execute(
        intake_id=_INTAKE_ID,
        title="Extracted Giants title",
        published_at=None,
        description=None,
    )

    assert result.metadata.status is NewsMetadataStatus.EXTRACTED
    assert result.processing_job.status is NewsProcessingStatus.COMPLETED
    assert result.processing_job.attempt_count == 1
    assert result.processing_job.started_at == _STARTED_AT


def test_unavailable_enrichment_completes_job() -> None:
    result = CompleteUnavailableNewsMetadataEnrichment(
        metadata_repository=FakeMetadataRepository(_pending_metadata()),
        job_repository=FakeJobRepository(_pending_job()),
        clock=lambda: _COMPLETED_AT,
    ).execute(
        intake_id=_INTAKE_ID,
        reason="Source returned HTTP 403",
    )

    assert result.metadata.status is NewsMetadataStatus.UNAVAILABLE
    assert result.metadata.failure_reason == ("Source returned HTTP 403")
    assert result.processing_job.status is NewsProcessingStatus.COMPLETED


def test_failed_enrichment_fails_metadata_and_job() -> None:
    result = FailNewsMetadataEnrichment(
        metadata_repository=FakeMetadataRepository(_pending_metadata()),
        job_repository=FakeJobRepository(_pending_job()),
        clock=lambda: _COMPLETED_AT,
    ).execute(
        intake_id=_INTAKE_ID,
        reason="Metadata parser failed",
    )

    assert result.metadata.status is NewsMetadataStatus.FAILED
    assert result.processing_job.status is NewsProcessingStatus.FAILED
    assert result.processing_job.last_error == ("Metadata parser failed")


def test_enrichment_rejects_missing_metadata() -> None:
    with pytest.raises(
        NewsMetadataEnrichmentTargetNotFoundError,
        match="Article metadata",
    ):
        CompleteManualNewsMetadataEnrichment(
            metadata_repository=FakeMetadataRepository(None),
            job_repository=FakeJobRepository(_pending_job()),
            clock=lambda: _COMPLETED_AT,
        ).execute(
            intake_id=_INTAKE_ID,
            title="Manual title",
            published_at=None,
            description=None,
        )


def test_enrichment_rejects_missing_processing_job() -> None:
    with pytest.raises(
        NewsMetadataEnrichmentTargetNotFoundError,
        match="Processing job",
    ):
        CompleteManualNewsMetadataEnrichment(
            metadata_repository=FakeMetadataRepository(_pending_metadata()),
            job_repository=FakeJobRepository(None),
            clock=lambda: _COMPLETED_AT,
        ).execute(
            intake_id=_INTAKE_ID,
            title="Manual title",
            published_at=None,
            description=None,
        )


def test_manual_enrichment_replaces_unavailable_metadata() -> None:
    unavailable = _pending_metadata().mark_unavailable(
        reason="Source returned HTTP 403",
        updated_at=_STARTED_AT,
    )
    completed_job = _pending_job().start(started_at=_STARTED_AT).complete(completed_at=_STARTED_AT)

    result = CompleteManualNewsMetadataEnrichment(
        metadata_repository=FakeMetadataRepository(unavailable),
        job_repository=FakeJobRepository(completed_job),
        clock=lambda: _COMPLETED_AT,
    ).execute(
        intake_id=_INTAKE_ID,
        title="Manually confirmed Giants title",
        published_at=_PUBLISHED_AT,
        description=None,
    )

    assert result.metadata.status is NewsMetadataStatus.MANUAL
    assert result.metadata.title == ("Manually confirmed Giants title")
    assert result.metadata.failure_reason is None
    assert result.processing_job == completed_job
