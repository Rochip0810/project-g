from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.analyze_priority import (
    AnalyzeNewsPriority,
    NewsPriorityAnalysisNotFoundError,
    NewsPriorityMetadataNotReadyError,
    NewsPriorityRelevanceNotReadyError,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceDecision,
)
from project_g.ports.news_priority import (
    NewsPriorityAnalyzerInput,
    NewsPriorityAnalyzerResult,
)

_INTAKE_ID = UUID("5b8ba00c-d3f4-416d-b19c-b2f281ab0f47")
_METADATA_ID = UUID("b35d37ea-122a-47d5-beb2-96df30e6e842")
_RELEVANCE_ID = UUID("2f510195-a0d0-4fc9-bd11-152342632f2b")
_PRIORITY_ID = UUID("3f510195-a0d0-4fc9-bd11-152342632f2b")

_CREATED_AT = datetime(
    2026,
    8,
    21,
    6,
    0,
    tzinfo=UTC,
)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)


class FakeIntakeRepository:
    def __init__(
        self,
        intake: ManualNewsIntake | None,
    ) -> None:
        self.intake = intake

    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        self.intake = intake
        return intake

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> ManualNewsIntake | None:
        if self.intake is not None and self.intake.intake_id == intake_id:
            return self.intake

        return None

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        if self.intake is not None and self.intake.canonical_url == canonical_url:
            return self.intake

        return None

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        return self.get_by_canonical_url(canonical_url) is not None


class FakeMetadataRepository:
    def __init__(
        self,
        metadata: NewsArticleMetadata | None,
    ) -> None:
        self.metadata = metadata

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


class FakeRelevanceRepository:
    def __init__(
        self,
        analysis: NewsRelevanceAnalysis | None,
    ) -> None:
        self.analysis = analysis

    def add(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        self.analysis = analysis
        return analysis

    def update(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        self.analysis = analysis
        return analysis

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        if self.analysis is not None and self.analysis.analysis_id == analysis_id:
            return self.analysis

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        if self.analysis is not None and self.analysis.intake_id == intake_id:
            return self.analysis

        return None


class FakePriorityRepository:
    def __init__(
        self,
        analysis: NewsPriorityAnalysis | None,
    ) -> None:
        self.analysis = analysis

    def add(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        self.analysis = analysis
        return analysis

    def update(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        self.analysis = analysis
        return analysis

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        if self.analysis is not None and self.analysis.analysis_id == analysis_id:
            return self.analysis

        return None

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        if self.analysis is not None and self.analysis.intake_id == intake_id:
            return self.analysis

        return None


class FakeAnalyzer:
    def __init__(
        self,
        *,
        score: int = 88,
    ) -> None:
        self.score = score
        self.received: NewsPriorityAnalyzerInput | None = None

    def analyze(
        self,
        input_data: NewsPriorityAnalyzerInput,
    ) -> NewsPriorityAnalyzerResult:
        self.received = input_data

        return NewsPriorityAnalyzerResult(
            priority_score=self.score,
            reason="Project Gで優先して扱う価値が高い。",
        )


def _intake() -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="hochi_giants_articles",
        submitted_url=("https://hochi.news/articles/test.html"),
        canonical_url=("https://hochi.news/articles/test.html"),
        submitted_at=_CREATED_AT,
    )


def _extracted_metadata() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    ).record_extracted(
        title="【巨人】主力選手が決勝本塁打",
        published_at=None,
        description="巨人の試合で主力選手が活躍した。",
        updated_at=_UPDATED_AT,
    )


def _pending_metadata() -> NewsArticleMetadata:
    return NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _analyzed_relevance(
    *,
    score: int = 95,
    decision: NewsRelevanceDecision = (NewsRelevanceDecision.ACCEPTED),
) -> NewsRelevanceAnalysis:
    return NewsRelevanceAnalysis.pending(
        analysis_id=_RELEVANCE_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    ).record_analyzed(
        relevance_score=score,
        decision=decision,
        reason="巨人に直接関係する記事。",
        updated_at=_UPDATED_AT,
    )


def _pending_relevance() -> NewsRelevanceAnalysis:
    return NewsRelevanceAnalysis.pending(
        analysis_id=_RELEVANCE_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _failed_relevance() -> NewsRelevanceAnalysis:
    return NewsRelevanceAnalysis.pending(
        analysis_id=_RELEVANCE_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    ).mark_failed(
        reason="AI request failed",
        updated_at=_UPDATED_AT,
    )


def _pending_priority() -> NewsPriorityAnalysis:
    return NewsPriorityAnalysis.pending(
        analysis_id=_PRIORITY_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _service(
    *,
    metadata: NewsArticleMetadata,
    relevance: NewsRelevanceAnalysis,
    priority: NewsPriorityAnalysis | None,
    analyzer: FakeAnalyzer,
) -> AnalyzeNewsPriority:
    return AnalyzeNewsPriority(
        intake_repository=FakeIntakeRepository(_intake()),
        metadata_repository=FakeMetadataRepository(metadata),
        relevance_repository=FakeRelevanceRepository(relevance),
        priority_repository=FakePriorityRepository(priority),
        analyzer=analyzer,
        clock=lambda: _UPDATED_AT + timedelta(minutes=1),
    )


def test_service_analyzes_accepted_news() -> None:
    analyzer = FakeAnalyzer()

    service = _service(
        metadata=_extracted_metadata(),
        relevance=_analyzed_relevance(),
        priority=_pending_priority(),
        analyzer=analyzer,
    )

    result = service.execute(_INTAKE_ID)

    assert result.analysis.status is NewsPriorityStatus.ANALYZED
    assert result.analysis.priority_score == 88
    assert result.analysis.reason == "Project Gで優先して扱う価値が高い。"

    assert analyzer.received is not None
    assert analyzer.received.source_id == "hochi_giants_articles"
    assert analyzer.received.title == "【巨人】主力選手が決勝本塁打"
    assert analyzer.received.relevance_score == 95
    assert analyzer.received.relevance_decision is NewsRelevanceDecision.ACCEPTED


def test_service_analyzes_review_news() -> None:
    analyzer = FakeAnalyzer(score=60)

    service = _service(
        metadata=_extracted_metadata(),
        relevance=_analyzed_relevance(
            score=55,
            decision=NewsRelevanceDecision.REVIEW,
        ),
        priority=_pending_priority(),
        analyzer=analyzer,
    )

    result = service.execute(_INTAKE_ID)

    assert result.analysis.priority_score == 60
    assert analyzer.received is not None
    assert analyzer.received.relevance_decision is NewsRelevanceDecision.REVIEW


def test_rejected_relevance_is_not_analyzed() -> None:
    analyzer = FakeAnalyzer()

    service = _service(
        metadata=_extracted_metadata(),
        relevance=_analyzed_relevance(
            score=20,
            decision=NewsRelevanceDecision.REJECTED,
        ),
        priority=None,
        analyzer=analyzer,
    )

    with pytest.raises(
        NewsPriorityRelevanceNotReadyError,
    ):
        service.execute(_INTAKE_ID)

    assert analyzer.received is None


@pytest.mark.parametrize(
    "relevance",
    [
        _pending_relevance(),
        _failed_relevance(),
    ],
)
def test_unfinished_relevance_is_not_analyzed(
    relevance: NewsRelevanceAnalysis,
) -> None:
    analyzer = FakeAnalyzer()

    service = _service(
        metadata=_extracted_metadata(),
        relevance=relevance,
        priority=_pending_priority(),
        analyzer=analyzer,
    )

    with pytest.raises(
        NewsPriorityRelevanceNotReadyError,
    ):
        service.execute(_INTAKE_ID)

    assert analyzer.received is None


def test_missing_priority_analysis_is_rejected() -> None:
    analyzer = FakeAnalyzer()

    service = _service(
        metadata=_extracted_metadata(),
        relevance=_analyzed_relevance(),
        priority=None,
        analyzer=analyzer,
    )

    with pytest.raises(
        NewsPriorityAnalysisNotFoundError,
    ):
        service.execute(_INTAKE_ID)

    assert analyzer.received is None


def test_pending_metadata_is_not_analyzed() -> None:
    analyzer = FakeAnalyzer()

    service = _service(
        metadata=_pending_metadata(),
        relevance=_analyzed_relevance(),
        priority=_pending_priority(),
        analyzer=analyzer,
    )

    with pytest.raises(
        NewsPriorityMetadataNotReadyError,
    ):
        service.execute(_INTAKE_ID)

    assert analyzer.received is None
