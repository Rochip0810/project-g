from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from project_g.application.news.relevance_policy import (
    decide_news_relevance,
)
from project_g.domain.news.article_metadata import (
    NewsMetadataStatus,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)
from project_g.ports.news_relevance import (
    NewsRelevanceAnalyzer,
    NewsRelevanceAnalyzerInput,
    NewsRelevanceAnalyzerResult,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeRepository,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataRepository,
)
from project_g.ports.repositories.news_relevance_analyses import (
    NewsRelevanceAnalysisRepository,
)

Clock = Callable[[], datetime]

_ANALYZABLE_METADATA_STATUSES = frozenset(
    {
        NewsMetadataStatus.EXTRACTED,
        NewsMetadataStatus.MANUAL,
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsRelevanceIntakeNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News intake was not found: {intake_id}")
        self.intake_id = intake_id


class NewsRelevanceMetadataNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News metadata was not found for intake: {intake_id}")
        self.intake_id = intake_id


class NewsRelevanceAnalysisNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Relevance analysis was not found for intake: {intake_id}")
        self.intake_id = intake_id


class NewsRelevanceMetadataNotReadyError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News metadata is not ready for relevance analysis: {intake_id}")
        self.intake_id = intake_id


@dataclass(frozen=True, slots=True)
class AnalyzeNewsRelevanceResult:
    analysis: NewsRelevanceAnalysis
    analyzer_result: NewsRelevanceAnalyzerResult


class AnalyzeNewsRelevance:
    def __init__(
        self,
        *,
        intake_repository: ManualNewsIntakeRepository,
        metadata_repository: NewsArticleMetadataRepository,
        relevance_repository: NewsRelevanceAnalysisRepository,
        analyzer: NewsRelevanceAnalyzer,
        clock: Clock = _utc_now,
    ) -> None:
        self._intake_repository = intake_repository
        self._metadata_repository = metadata_repository
        self._relevance_repository = relevance_repository
        self._analyzer = analyzer
        self._clock = clock

    def execute(
        self,
        intake_id: UUID,
    ) -> AnalyzeNewsRelevanceResult:
        intake = self._intake_repository.get_by_intake_id(intake_id)

        if intake is None:
            raise NewsRelevanceIntakeNotFoundError(intake_id)

        metadata = self._metadata_repository.get_by_intake_id(intake_id)

        if metadata is None:
            raise NewsRelevanceMetadataNotFoundError(intake_id)

        if metadata.status not in _ANALYZABLE_METADATA_STATUSES or metadata.title is None:
            raise NewsRelevanceMetadataNotReadyError(intake_id)

        analysis = self._relevance_repository.get_by_intake_id(intake_id)

        if analysis is None:
            raise NewsRelevanceAnalysisNotFoundError(intake_id)

        analyzer_result = self._analyzer.analyze(
            NewsRelevanceAnalyzerInput(
                source_id=intake.source_id,
                title=metadata.title,
                description=metadata.description,
            )
        )

        decision = decide_news_relevance(analyzer_result.relevance_score)

        analyzed = analysis.record_analyzed(
            relevance_score=analyzer_result.relevance_score,
            decision=decision,
            reason=analyzer_result.reason,
            updated_at=self._clock(),
        )

        stored = self._relevance_repository.update(analyzed)

        return AnalyzeNewsRelevanceResult(
            analysis=stored,
            analyzer_result=analyzer_result,
        )
