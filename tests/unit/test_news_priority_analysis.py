from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from project_g.domain.news.priority_analysis import (
    InvalidNewsPriorityAnalysisError,
    InvalidNewsPriorityTransitionError,
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)

NOW = datetime(
    2026,
    8,
    18,
    12,
    0,
    tzinfo=UTC,
)


def test_pending_priority_analysis() -> None:
    analysis_id = uuid4()
    intake_id = uuid4()

    analysis = NewsPriorityAnalysis.pending(
        analysis_id=analysis_id,
        intake_id=intake_id,
        created_at=NOW,
    )

    assert analysis.analysis_id == analysis_id
    assert analysis.intake_id == intake_id
    assert analysis.status is NewsPriorityStatus.PENDING
    assert analysis.priority_score is None
    assert analysis.reason is None
    assert analysis.failure_reason is None
    assert analysis.created_at == NOW
    assert analysis.updated_at == NOW


def test_pending_can_be_recorded_as_analyzed() -> None:
    analysis = NewsPriorityAnalysis.pending(
        analysis_id=uuid4(),
        intake_id=uuid4(),
        created_at=NOW,
    )

    updated_at = NOW + timedelta(minutes=1)

    analyzed = analysis.record_analyzed(
        priority_score=88,
        reason="投稿候補として価値が高い",
        updated_at=updated_at,
    )

    assert analyzed.status is NewsPriorityStatus.ANALYZED
    assert analyzed.priority_score == 88
    assert analyzed.reason == "投稿候補として価値が高い"
    assert analyzed.failure_reason is None
    assert analyzed.updated_at == updated_at


def test_pending_can_be_marked_failed() -> None:
    analysis = NewsPriorityAnalysis.pending(
        analysis_id=uuid4(),
        intake_id=uuid4(),
        created_at=NOW,
    )

    failed = analysis.mark_failed(
        reason="AI request failed",
        updated_at=NOW + timedelta(minutes=1),
    )

    assert failed.status is NewsPriorityStatus.FAILED
    assert failed.priority_score is None
    assert failed.reason is None
    assert failed.failure_reason == "AI request failed"


@pytest.mark.parametrize(
    "priority_score",
    [-1, 101],
)
def test_priority_score_must_be_between_zero_and_one_hundred(
    priority_score: int,
) -> None:
    with pytest.raises(
        InvalidNewsPriorityAnalysisError,
        match="priority_score must be between 0 and 100",
    ):
        NewsPriorityAnalysis(
            analysis_id=uuid4(),
            intake_id=uuid4(),
            status=NewsPriorityStatus.ANALYZED,
            priority_score=priority_score,
            reason="reason",
            failure_reason=None,
            created_at=NOW,
            updated_at=NOW,
        )


def test_analyzed_priority_requires_reason() -> None:
    with pytest.raises(
        InvalidNewsPriorityAnalysisError,
        match="must include reason",
    ):
        NewsPriorityAnalysis(
            analysis_id=uuid4(),
            intake_id=uuid4(),
            status=NewsPriorityStatus.ANALYZED,
            priority_score=80,
            reason=None,
            failure_reason=None,
            created_at=NOW,
            updated_at=NOW,
        )


def test_failed_priority_requires_failure_reason() -> None:
    with pytest.raises(
        InvalidNewsPriorityAnalysisError,
        match="must include failure_reason",
    ):
        NewsPriorityAnalysis(
            analysis_id=uuid4(),
            intake_id=uuid4(),
            status=NewsPriorityStatus.FAILED,
            priority_score=None,
            reason=None,
            failure_reason=None,
            created_at=NOW,
            updated_at=NOW,
        )


def test_non_pending_priority_cannot_transition_again() -> None:
    analysis = NewsPriorityAnalysis.pending(
        analysis_id=uuid4(),
        intake_id=uuid4(),
        created_at=NOW,
    ).record_analyzed(
        priority_score=75,
        reason="priority reason",
        updated_at=NOW + timedelta(minutes=1),
    )

    with pytest.raises(
        InvalidNewsPriorityTransitionError,
        match="only transition from pending",
    ):
        analysis.mark_failed(
            reason="late failure",
            updated_at=NOW + timedelta(minutes=2),
        )


def test_created_at_must_be_timezone_aware() -> None:
    naive = datetime(
        2026,
        8,
        18,
        12,
        0,
    )

    with pytest.raises(
        InvalidNewsPriorityAnalysisError,
        match="created_at must be timezone-aware",
    ):
        NewsPriorityAnalysis.pending(
            analysis_id=uuid4(),
            intake_id=uuid4(),
            created_at=naive,
        )
