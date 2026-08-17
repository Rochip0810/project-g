from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.relevance_analysis import (
    InvalidNewsRelevanceAnalysisError,
    InvalidNewsRelevanceTransitionError,
    NewsRelevanceAnalysis,
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)

_ANALYSIS_ID = UUID("68031081-7661-4d78-bef6-f3246fa74111")
_INTAKE_ID = UUID("b4916047-8404-4abc-af7c-2e48588fb145")
_CREATED_AT = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)


def _pending() -> NewsRelevanceAnalysis:
    return NewsRelevanceAnalysis.pending(
        analysis_id=_ANALYSIS_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_pending_factory_creates_empty_analysis() -> None:
    analysis = _pending()

    assert analysis.status is NewsRelevanceStatus.PENDING
    assert analysis.relevance_score is None
    assert analysis.decision is None
    assert analysis.reason is None
    assert analysis.failure_reason is None


def test_pending_analysis_can_record_analyzed_result() -> None:
    analysis = _pending().record_analyzed(
        relevance_score=95,
        decision=NewsRelevanceDecision.ACCEPTED,
        reason="  Directly concerns the Giants.  ",
        updated_at=_UPDATED_AT,
    )

    assert analysis.status is NewsRelevanceStatus.ANALYZED
    assert analysis.relevance_score == 95
    assert analysis.decision is NewsRelevanceDecision.ACCEPTED
    assert analysis.reason == "Directly concerns the Giants."
    assert analysis.failure_reason is None


def test_pending_analysis_can_be_marked_failed() -> None:
    analysis = _pending().mark_failed(
        reason="  AI analysis failed  ",
        updated_at=_UPDATED_AT,
    )

    assert analysis.status is NewsRelevanceStatus.FAILED
    assert analysis.failure_reason == "AI analysis failed"


@pytest.mark.parametrize(
    "score",
    [-1, 101],
)
def test_analysis_rejects_score_outside_valid_range(
    score: int,
) -> None:
    with pytest.raises(
        InvalidNewsRelevanceAnalysisError,
        match="between 0 and 100",
    ):
        _pending().record_analyzed(
            relevance_score=score,
            decision=NewsRelevanceDecision.ACCEPTED,
            reason="Relevant article",
            updated_at=_UPDATED_AT,
        )


def test_analyzed_result_requires_reason() -> None:
    with pytest.raises(
        InvalidNewsRelevanceAnalysisError,
        match="must include reason",
    ):
        _pending().record_analyzed(
            relevance_score=80,
            decision=NewsRelevanceDecision.ACCEPTED,
            reason="   ",
            updated_at=_UPDATED_AT,
        )


def test_analyzed_analysis_cannot_transition_again() -> None:
    analysis = _pending().record_analyzed(
        relevance_score=80,
        decision=NewsRelevanceDecision.ACCEPTED,
        reason="Giants article",
        updated_at=_UPDATED_AT,
    )

    with pytest.raises(
        InvalidNewsRelevanceTransitionError,
        match="only transition from pending",
    ):
        analysis.mark_failed(
            reason="Later failure",
            updated_at=_UPDATED_AT + timedelta(minutes=1),
        )


def test_analysis_rejects_naive_created_at() -> None:
    with pytest.raises(
        InvalidNewsRelevanceAnalysisError,
        match="created_at must be timezone-aware",
    ):
        NewsRelevanceAnalysis.pending(
            analysis_id=_ANALYSIS_ID,
            intake_id=_INTAKE_ID,
            created_at=datetime(2026, 8, 12, 10, 0),
        )


def test_analysis_rejects_updated_at_before_creation() -> None:
    with pytest.raises(
        InvalidNewsRelevanceAnalysisError,
        match="updated_at must not be earlier",
    ):
        _pending().mark_failed(
            reason="Failed",
            updated_at=_CREATED_AT - timedelta(seconds=1),
        )
