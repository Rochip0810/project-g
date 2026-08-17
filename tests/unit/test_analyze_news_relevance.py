from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.analyze_relevance import (
    AnalyzeNewsRelevance,
    NewsRelevanceAnalysisNotFoundError,
    NewsRelevanceMetadataNotReadyError,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.ports.news_relevance import (
    NewsRelevanceAnalyzerInput,
    NewsRelevanceAnalyzerResult,
)

_INTAKE_ID = UUID("4b8ba00c-d3f4-416d-b19c-b2f281ab0f47")
_METADATA_ID = UUID("a35d37ea-122a-47d5-beb2-96df30e6e842")
_ANALYSIS_ID = UUID("1f510195-a0d0-4fc9-bd11-152342632f2b")

_CREATED_AT = datetime(
    2026,
    8,
    12,
    14,
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


class FakeAnalyzer:
    def __init__(
        self,
        *,
        score: int = 95,
    ) -> None:
        self.score = score
        self.received: NewsRelevanceAnalyzerInput | None = None

    def analyze(
        self,
        input_data: NewsRelevanceAnalyzerInput,
    ) -> NewsRelevanceAnalyzerResult:
        self.received = input_data

        return NewsRelevanceAnalyzerResult(
            relevance_score=self.score,
            reason="Directly concerns the Yomiuri Giants.",
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
        title="【巨人】ダルベックが20号",
        published_at=None,
        description="巨人の試合に関する記事です。",
        updated_at=_UPDATED_AT,
    )


def _pending_analysis() -> NewsRelevanceAnalysis:
    return NewsRelevanceAnalysis.pending(
        analysis_id=_ANALYSIS_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_service_analyzes_ready_news() -> None:
    analyzer = FakeAnalyzer()

    service = AnalyzeNewsRelevance(
        intake_repository=FakeIntakeRepository(_intake()),
        metadata_repository=FakeMetadataRepository(_extracted_metadata()),
        relevance_repository=FakeRelevanceRepository(_pending_analysis()),
        analyzer=analyzer,
        clock=lambda: _UPDATED_AT,
    )

    result = service.execute(_INTAKE_ID)

    assert result.analysis.status is NewsRelevanceStatus.ANALYZED
    assert result.analysis.relevance_score == 95
    assert result.analysis.decision is NewsRelevanceDecision.ACCEPTED
    assert result.analysis.reason == "Directly concerns the Yomiuri Giants."

    assert analyzer.received is not None
    assert analyzer.received.source_id == ("hochi_giants_articles")
    assert analyzer.received.title == ("【巨人】ダルベックが20号")


def test_service_uses_policy_for_review_score() -> None:
    service = AnalyzeNewsRelevance(
        intake_repository=FakeIntakeRepository(_intake()),
        metadata_repository=FakeMetadataRepository(_extracted_metadata()),
        relevance_repository=FakeRelevanceRepository(_pending_analysis()),
        analyzer=FakeAnalyzer(score=55),
        clock=lambda: _UPDATED_AT,
    )

    result = service.execute(_INTAKE_ID)

    assert result.analysis.decision is NewsRelevanceDecision.REVIEW


def test_pending_metadata_is_not_analyzed() -> None:
    metadata = NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )

    service = AnalyzeNewsRelevance(
        intake_repository=FakeIntakeRepository(_intake()),
        metadata_repository=FakeMetadataRepository(metadata),
        relevance_repository=FakeRelevanceRepository(_pending_analysis()),
        analyzer=FakeAnalyzer(),
        clock=lambda: _UPDATED_AT,
    )

    with pytest.raises(
        NewsRelevanceMetadataNotReadyError,
    ):
        service.execute(_INTAKE_ID)


def test_missing_analysis_is_rejected() -> None:
    service = AnalyzeNewsRelevance(
        intake_repository=FakeIntakeRepository(_intake()),
        metadata_repository=FakeMetadataRepository(_extracted_metadata()),
        relevance_repository=FakeRelevanceRepository(None),
        analyzer=FakeAnalyzer(),
        clock=lambda: _UPDATED_AT,
    )

    with pytest.raises(
        NewsRelevanceAnalysisNotFoundError,
    ):
        service.execute(_INTAKE_ID)
