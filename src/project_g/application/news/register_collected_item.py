from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from project_g.domain.news import (
    CollectedNewsItem,
    NewsSource,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
    ManualNewsIntakeRepository,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataRepository,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobRepository,
)
from project_g.ports.repositories.news_relevance_analyses import (
    NewsRelevanceAnalysisRepository,
)

IdFactory = Callable[[], UUID]


class CollectedNewsRegistrationStatus(StrEnum):
    REGISTERED = "registered"
    DUPLICATE = "duplicate"


class CollectedNewsItemMismatchError(ValueError):
    """Raised when collector data disagrees with the registered source."""


@dataclass(frozen=True, slots=True)
class RegisterCollectedNewsItemResult:
    status: CollectedNewsRegistrationStatus
    canonical_url: str
    intake: ManualNewsIntake | None = None
    processing_job: NewsProcessingJob | None = None
    article_metadata: NewsArticleMetadata | None = None
    relevance_analysis: NewsRelevanceAnalysis | None = None


class RegisterCollectedNewsItem:
    def __init__(
        self,
        *,
        sources: tuple[NewsSource, ...],
        intake_repository: ManualNewsIntakeRepository,
        processing_job_repository: NewsProcessingJobRepository,
        metadata_repository: NewsArticleMetadataRepository,
        relevance_repository: NewsRelevanceAnalysisRepository,
        intake_id_factory: IdFactory = uuid4,
        processing_job_id_factory: IdFactory = uuid4,
        metadata_id_factory: IdFactory = uuid4,
        relevance_analysis_id_factory: IdFactory = uuid4,
    ) -> None:
        self._sources = {source.source_id: source for source in sources}
        self._intake_repository = intake_repository
        self._processing_job_repository = processing_job_repository
        self._metadata_repository = metadata_repository
        self._relevance_repository = relevance_repository
        self._intake_id_factory = intake_id_factory
        self._processing_job_id_factory = processing_job_id_factory
        self._metadata_id_factory = metadata_id_factory
        self._relevance_analysis_id_factory = relevance_analysis_id_factory

    def execute(
        self,
        item: CollectedNewsItem,
    ) -> RegisterCollectedNewsItemResult:
        source = self._sources.get(item.source_id)

        if source is None:
            raise CollectedNewsItemMismatchError(
                "Collected item source does not match a registered news source"
            )

        if not self._matches_source_host(
            source,
            item.source_url,
        ):
            raise CollectedNewsItemMismatchError(
                "Collected item source does not match the registered news source"
            )

        if not self._matches_source_host(
            source,
            item.canonical_url,
        ):
            raise CollectedNewsItemMismatchError(
                "Collected item source does not match the registered news source"
            )

        if self._intake_repository.exists_by_canonical_url(item.canonical_url):
            return RegisterCollectedNewsItemResult(
                status=(CollectedNewsRegistrationStatus.DUPLICATE),
                canonical_url=item.canonical_url,
            )

        intake = ManualNewsIntake(
            intake_id=self._intake_id_factory(),
            source_id=source.source_id,
            submitted_url=item.source_url,
            canonical_url=item.canonical_url,
            submitted_at=item.collected_at,
        )

        try:
            stored_intake = self._intake_repository.add(intake)
        except ManualNewsIntakeAlreadyExistsError:
            return RegisterCollectedNewsItemResult(
                status=(CollectedNewsRegistrationStatus.DUPLICATE),
                canonical_url=item.canonical_url,
            )

        processing_job = NewsProcessingJob.pending(
            job_id=self._processing_job_id_factory(),
            intake_id=stored_intake.intake_id,
            created_at=item.collected_at,
        )
        stored_job = self._processing_job_repository.add(processing_job)

        metadata = NewsArticleMetadata.pending(
            metadata_id=self._metadata_id_factory(),
            intake_id=stored_intake.intake_id,
            created_at=item.collected_at,
        )
        stored_metadata = self._metadata_repository.add(metadata)

        relevance_analysis = NewsRelevanceAnalysis.pending(
            analysis_id=self._relevance_analysis_id_factory(),
            intake_id=stored_intake.intake_id,
            created_at=item.collected_at,
        )
        stored_relevance_analysis = self._relevance_repository.add(relevance_analysis)

        return RegisterCollectedNewsItemResult(
            status=(CollectedNewsRegistrationStatus.REGISTERED),
            canonical_url=item.canonical_url,
            intake=stored_intake,
            processing_job=stored_job,
            article_metadata=stored_metadata,
            relevance_analysis=stored_relevance_analysis,
        )

    @staticmethod
    def _matches_source_host(
        source: NewsSource,
        url: str,
    ) -> bool:
        source_host = (urlsplit(source.base_url).hostname or "").casefold()
        parsed = urlsplit(url)
        item_host = (parsed.hostname or "").casefold()

        return parsed.scheme == "https" and bool(source_host) and item_host == source_host
