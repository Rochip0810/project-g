from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.article_metadata import (
    NewsMetadataStatus,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.ports.news_priority import (
    NewsPriorityAnalyzer,
    NewsPriorityAnalyzerInput,
    NewsPriorityAnalyzerResult,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeRepository,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataRepository,
)
from project_g.ports.repositories.news_priority_analyses import (
    NewsPriorityAnalysisRepository,
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

_ELIGIBLE_RELEVANCE_DECISIONS = frozenset(
    {
        NewsRelevanceDecision.ACCEPTED,
        NewsRelevanceDecision.REVIEW,
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsPriorityIntakeNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News intake was not found: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityMetadataNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News metadata was not found for intake: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityMetadataNotReadyError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"News metadata is not ready for priority analysis: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityRelevanceNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Relevance analysis was not found for intake: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityRelevanceNotReadyError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Relevance analysis is not eligible for priority analysis: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityAnalysisNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Priority analysis was not found for intake: {intake_id}")
        self.intake_id = intake_id


@dataclass(frozen=True, slots=True)
class AnalyzeNewsPriorityResult:
    analysis: NewsPriorityAnalysis
    analyzer_result: NewsPriorityAnalyzerResult


class AnalyzeNewsPriority:
    def __init__(
        self,
        *,
        intake_repository: ManualNewsIntakeRepository,
        metadata_repository: NewsArticleMetadataRepository,
        relevance_repository: NewsRelevanceAnalysisRepository,
        priority_repository: NewsPriorityAnalysisRepository,
        analyzer: NewsPriorityAnalyzer,
        clock: Clock = _utc_now,
    ) -> None:
        self._intake_repository = intake_repository
        self._metadata_repository = metadata_repository
        self._relevance_repository = relevance_repository
        self._priority_repository = priority_repository
        self._analyzer = analyzer
        self._clock = clock

    def execute(
        self,
        intake_id: UUID,
    ) -> AnalyzeNewsPriorityResult:
        intake = self._intake_repository.get_by_intake_id(intake_id)

        if intake is None:
            raise NewsPriorityIntakeNotFoundError(intake_id)

        metadata = self._metadata_repository.get_by_intake_id(intake_id)

        if metadata is None:
            raise NewsPriorityMetadataNotFoundError(intake_id)

        if metadata.status not in _ANALYZABLE_METADATA_STATUSES or metadata.title is None:
            raise NewsPriorityMetadataNotReadyError(intake_id)

        relevance = self._relevance_repository.get_by_intake_id(intake_id)

        if relevance is None:
            raise NewsPriorityRelevanceNotFoundError(intake_id)

        if (
            relevance.status is not NewsRelevanceStatus.ANALYZED
            or relevance.relevance_score is None
            or relevance.decision not in _ELIGIBLE_RELEVANCE_DECISIONS
        ):
            raise NewsPriorityRelevanceNotReadyError(intake_id)

        analysis = self._priority_repository.get_by_intake_id(intake_id)

        if analysis is None:
            raise NewsPriorityAnalysisNotFoundError(intake_id)

        analyzer_result = self._analyzer.analyze(
            NewsPriorityAnalyzerInput(
                source_id=intake.source_id,
                title=metadata.title,
                description=metadata.description,
                relevance_score=relevance.relevance_score,
                relevance_decision=relevance.decision,
            )
        )

        analyzed = analysis.record_analyzed(
            priority_score=analyzer_result.priority_score,
            reason=analyzer_result.reason,
            updated_at=self._clock(),
        )

        stored = self._priority_repository.update(analyzed)

        return AnalyzeNewsPriorityResult(
            analysis=stored,
            analyzer_result=analyzer_result,
        )
