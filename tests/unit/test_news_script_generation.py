from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.script_generation import (
    InvalidNewsScriptGenerationError,
    InvalidNewsScriptGenerationTransitionError,
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)

_GENERATION_ID = UUID("1eb3c6ac-c34f-457a-96de-f1fcfb61c17e")
_INTAKE_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")

_CREATED_AT = datetime(2026, 9, 6, 7, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)
_RETRY_STARTED_AT = _COMPLETED_AT + timedelta(minutes=1)


def _pending() -> NewsScriptGeneration:
    return NewsScriptGeneration.pending(
        generation_id=_GENERATION_ID,
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=87,
        created_at=_CREATED_AT,
    )


def _generating() -> NewsScriptGeneration:
    return _pending().start(
        started_at=_STARTED_AT,
    )


def _evidence() -> tuple[NewsScriptEvidenceSnapshot, ...]:
    return (
        NewsScriptEvidenceSnapshot(
            text=(
                "2026年8月15日のファーム戦で則本は勝投手となり、"
                "6回、84球、被安打9、被本塁打1、四球0、"
                "奪三振3、4失点(自責3)だった。"
            ),
            source_id="npb_official",
            source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            competition_level=CompetitionLevel.FARM,
            role=EvidenceRole.TARGET,
        ),
    )


def test_pending_factory_creates_unstarted_generation() -> None:
    generation = _pending()

    assert generation.generation_id == _GENERATION_ID
    assert generation.intake_id == _INTAKE_ID
    assert generation.generation_version == 1
    assert generation.ranking_score == 87
    assert generation.status is NewsScriptGenerationStatus.PENDING
    assert generation.attempt_count == 0
    assert generation.failure_reason is None

    assert generation.hook is None
    assert generation.main_narration is None
    assert generation.project_g_comment is None
    assert generation.closing is None
    assert generation.full_narration is None
    assert generation.evidence_snapshot is None

    assert generation.created_at == _CREATED_AT
    assert generation.started_at is None
    assert generation.completed_at is None
    assert generation.updated_at == _CREATED_AT


def test_pending_generation_can_start() -> None:
    generation = _generating()

    assert generation.status is NewsScriptGenerationStatus.GENERATING
    assert generation.attempt_count == 1
    assert generation.failure_reason is None
    assert generation.started_at == _STARTED_AT
    assert generation.completed_at is None
    assert generation.updated_at == _STARTED_AT


def test_generating_generation_can_record_generated_script() -> None:
    evidence = _evidence()

    generation = _generating().record_generated(
        hook="則本昂大が1軍に合流した。",
        main_narration="巨人の則本昂大投手が1軍に合流しました。",
        project_g_comment=(
            "ファームでは勝ち投手になってるけど、内容は手放しで安心できるもんやないな。"
        ),
        closing="今後の起用に注目です。",
        full_narration="完成したナレーション全文",
        evidence_snapshot=evidence,
        completed_at=_COMPLETED_AT,
    )

    assert generation.status is NewsScriptGenerationStatus.GENERATED
    assert generation.hook == "則本昂大が1軍に合流した。"
    assert generation.main_narration == "巨人の則本昂大投手が1軍に合流しました。"
    assert generation.project_g_comment == (
        "ファームでは勝ち投手になってるけど、内容は手放しで安心できるもんやないな。"
    )
    assert generation.closing == "今後の起用に注目です。"
    assert generation.full_narration == "完成したナレーション全文"
    assert generation.evidence_snapshot == evidence
    assert generation.failure_reason is None
    assert generation.completed_at == _COMPLETED_AT
    assert generation.updated_at == _COMPLETED_AT


def test_generating_generation_can_fail() -> None:
    generation = _generating().mark_failed(
        reason="  OpenAI request failed  ",
        completed_at=_COMPLETED_AT,
    )

    assert generation.status is NewsScriptGenerationStatus.FAILED
    assert generation.attempt_count == 1
    assert generation.failure_reason == "OpenAI request failed"

    assert generation.hook is None
    assert generation.main_narration is None
    assert generation.project_g_comment is None
    assert generation.closing is None
    assert generation.full_narration is None
    assert generation.evidence_snapshot is None

    assert generation.completed_at == _COMPLETED_AT
    assert generation.updated_at == _COMPLETED_AT


def test_failed_generation_can_retry() -> None:
    failed = _generating().mark_failed(
        reason="OpenAI request failed",
        completed_at=_COMPLETED_AT,
    )

    retrying = failed.start(
        started_at=_RETRY_STARTED_AT,
    )

    assert retrying.status is NewsScriptGenerationStatus.GENERATING
    assert retrying.attempt_count == 2
    assert retrying.failure_reason is None
    assert retrying.started_at == _RETRY_STARTED_AT
    assert retrying.completed_at is None
    assert retrying.updated_at == _RETRY_STARTED_AT


def test_generation_version_must_be_at_least_one() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="generation_version must be at least 1",
    ):
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_ID,
            intake_id=_INTAKE_ID,
            generation_version=0,
            ranking_score=87,
            created_at=_CREATED_AT,
        )


@pytest.mark.parametrize(
    "ranking_score",
    [-1, 101],
)
def test_ranking_score_must_be_between_zero_and_one_hundred(
    ranking_score: int,
) -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="ranking_score must be between 0 and 100",
    ):
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_ID,
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=ranking_score,
            created_at=_CREATED_AT,
        )


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="created_at must be timezone-aware",
    ):
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_ID,
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=87,
            created_at=datetime(2026, 9, 6, 7, 0),
        )


def test_completed_at_cannot_be_before_started_at() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="completed_at must not be earlier than started_at",
    ):
        _generating().mark_failed(
            reason="generation failed",
            completed_at=_CREATED_AT,
        )


def test_pending_generation_cannot_record_generated_script() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationTransitionError,
        match="must be generating",
    ):
        _pending().record_generated(
            hook="hook",
            main_narration="main",
            project_g_comment="comment",
            closing="closing",
            full_narration="full",
            evidence_snapshot=(),
            completed_at=_COMPLETED_AT,
        )


def test_generated_generation_cannot_start_again() -> None:
    generated = _generating().record_generated(
        hook="hook",
        main_narration="main",
        project_g_comment="comment",
        closing="closing",
        full_narration="full",
        evidence_snapshot=(),
        completed_at=_COMPLETED_AT,
    )

    with pytest.raises(
        InvalidNewsScriptGenerationTransitionError,
        match="only start from pending or failed",
    ):
        generated.start(
            started_at=_COMPLETED_AT + timedelta(minutes=1),
        )


def test_failure_reason_must_not_be_blank() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="failure_reason must not be empty",
    ):
        _generating().mark_failed(
            reason="   ",
            completed_at=_COMPLETED_AT,
        )


def test_generated_script_allows_empty_evidence_snapshot() -> None:
    generation = _generating().record_generated(
        hook="hook",
        main_narration="main",
        project_g_comment="comment",
        closing="closing",
        full_narration="full",
        evidence_snapshot=(),
        completed_at=_COMPLETED_AT,
    )

    assert generation.status is NewsScriptGenerationStatus.GENERATED
    assert generation.evidence_snapshot == ()
