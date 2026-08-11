from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.application.news.register_collected_item import (
    CollectedNewsItemMismatchError,
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItem,
)
from project_g.domain.news import CollectedNewsItem
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
)

_INTAKE_ID = UUID("cb28f4c0-75b2-442b-a004-43de5d2cb088")
_JOB_ID = UUID("0bc157ba-00be-4dbe-a254-cf6bb512c19a")
_METADATA_ID = UUID("7ea195d0-8b80-4893-bb08-e63ed597af68")

_COLLECTED_AT = datetime(
    2026,
    8,
    11,
    7,
    0,
    tzinfo=UTC,
)


class FakeIntakeRepository:
    def __init__(self) -> None:
        self.by_id: dict[UUID, ManualNewsIntake] = {}
        self.by_url: dict[str, ManualNewsIntake] = {}

    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        if intake.canonical_url in self.by_url:
            raise ManualNewsIntakeAlreadyExistsError(intake.canonical_url)

        self.by_id[intake.intake_id] = intake
        self.by_url[intake.canonical_url] = intake
        return intake

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> ManualNewsIntake | None:
        return self.by_id.get(intake_id)

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        return self.by_url.get(canonical_url)

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        return canonical_url in self.by_url


class FakeProcessingJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, NewsProcessingJob] = {}

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.jobs[job.job_id] = job
        return job

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        self.jobs[job.job_id] = job
        return job

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        return self.jobs.get(job_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        return next(
            (job for job in self.jobs.values() if job.intake_id == intake_id),
            None,
        )

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        return next(
            (job for job in self.jobs.values() if job.status is NewsProcessingStatus.PENDING),
            None,
        )


class FakeMetadataRepository:
    def __init__(self) -> None:
        self.records: dict[
            UUID,
            NewsArticleMetadata,
        ] = {}

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.records[metadata.metadata_id] = metadata
        return metadata

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        self.records[metadata.metadata_id] = metadata
        return metadata

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        return self.records.get(metadata_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        return next(
            (metadata for metadata in self.records.values() if metadata.intake_id == intake_id),
            None,
        )


def _item(
    *,
    source_id: str = "giants_official_news",
) -> CollectedNewsItem:
    return CollectedNewsItem(
        source_id=source_id,
        source_name="Giants Official News",
        title="Giants test article",
        source_url=("https://www.giants.jp/news/123456/"),
        canonical_url=("https://www.giants.jp/news/123456/"),
        collected_at=_COLLECTED_AT,
        published_at=_COLLECTED_AT,
        external_id="123456",
    )


def _service(
    intake_repository: FakeIntakeRepository,
    job_repository: FakeProcessingJobRepository,
    metadata_repository: FakeMetadataRepository,
) -> RegisterCollectedNewsItem:
    return RegisterCollectedNewsItem(
        sources=INITIAL_NEWS_SOURCES,
        intake_repository=intake_repository,
        processing_job_repository=job_repository,
        metadata_repository=metadata_repository,
        intake_id_factory=lambda: _INTAKE_ID,
        processing_job_id_factory=lambda: _JOB_ID,
        metadata_id_factory=lambda: _METADATA_ID,
    )


def test_new_collected_item_creates_all_records() -> None:
    intake_repository = FakeIntakeRepository()
    job_repository = FakeProcessingJobRepository()
    metadata_repository = FakeMetadataRepository()

    result = _service(
        intake_repository,
        job_repository,
        metadata_repository,
    ).execute(_item())

    assert result.status is CollectedNewsRegistrationStatus.REGISTERED
    assert result.intake is not None
    assert result.processing_job is not None
    assert result.article_metadata is not None

    assert result.intake.intake_id == _INTAKE_ID
    assert result.intake.canonical_url == ("https://www.giants.jp/news/123456/")

    assert result.processing_job.status is NewsProcessingStatus.PENDING
    assert result.article_metadata.status is NewsMetadataStatus.PENDING


def test_duplicate_collected_item_is_skipped() -> None:
    intake_repository = FakeIntakeRepository()
    intake_repository.add(
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id="giants_official_news",
            submitted_url=("https://www.giants.jp/news/123456/"),
            canonical_url=("https://www.giants.jp/news/123456/"),
            submitted_at=_COLLECTED_AT,
        )
    )

    job_repository = FakeProcessingJobRepository()
    metadata_repository = FakeMetadataRepository()

    result = _service(
        intake_repository,
        job_repository,
        metadata_repository,
    ).execute(_item())

    assert result.status is CollectedNewsRegistrationStatus.DUPLICATE
    assert result.processing_job is None
    assert result.article_metadata is None
    assert job_repository.jobs == {}
    assert metadata_repository.records == {}


def test_collected_item_source_mismatch_is_rejected() -> None:
    with pytest.raises(
        CollectedNewsItemMismatchError,
        match="source does not match",
    ):
        _service(
            FakeIntakeRepository(),
            FakeProcessingJobRepository(),
            FakeMetadataRepository(),
        ).execute(_item(source_id="npb_official_schedule"))


def test_hochi_article_outside_source_base_path_is_registered() -> None:
    intake_repository = FakeIntakeRepository()
    job_repository = FakeProcessingJobRepository()
    metadata_repository = FakeMetadataRepository()

    article_url = "https://hochi.news/articles/20260811-OHT1T51258.html"

    item = CollectedNewsItem(
        source_id="hochi_giants_articles",
        source_name="Sports Hochi Giants Articles",
        title="【巨人】テスト記事",
        source_url=article_url,
        canonical_url=article_url,
        collected_at=_COLLECTED_AT,
        published_at=_COLLECTED_AT,
        external_id="20260811-OHT1T51258",
    )

    result = _service(
        intake_repository,
        job_repository,
        metadata_repository,
    ).execute(item)

    assert result.status is CollectedNewsRegistrationStatus.REGISTERED
    assert result.intake is not None
    assert result.intake.source_id == "hochi_giants_articles"
    assert result.intake.canonical_url == article_url
