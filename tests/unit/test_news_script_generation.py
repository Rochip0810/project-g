from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.script_generation import (
    InvalidNewsScriptGenerationError,
    InvalidNewsScriptGenerationTransitionError,
    NewsScriptCharacter,
    NewsScriptDialogueLine,
    NewsScriptEmotion,
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


def test_generated_script_allows_missing_closing() -> None:
    generation = _generating().record_generated(
        hook="hook",
        main_narration="main",
        project_g_comment="comment",
        closing=None,
        full_narration="full",
        evidence_snapshot=(),
        completed_at=_COMPLETED_AT,
    )

    assert generation.status is NewsScriptGenerationStatus.GENERATED
    assert generation.closing is None


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


def test_dialogue_line_normalizes_text() -> None:
    line = NewsScriptDialogueLine(
        character=NewsScriptCharacter.JAN,
        emotion=NewsScriptEmotion.CRITICAL,
        intensity=4,
        break_character=False,
        text="  いや、これはさすがに同じミス多すぎるわ。  ",
    )

    assert line.text == "いや、これはさすがに同じミス多すぎるわ。"


@pytest.mark.parametrize(
    "intensity",
    [0, 6],
)
def test_dialogue_intensity_must_be_between_one_and_five(
    intensity: int,
) -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="dialogue intensity must be between 1 and 5",
    ):
        NewsScriptDialogueLine(
            character=NewsScriptCharacter.AN,
            emotion=NewsScriptEmotion.SUPPORTIVE,
            intensity=intensity,
            break_character=False,
            text="まだこれからやで。",
        )


def test_dialogue_text_must_not_be_blank() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="dialogue text must not be empty",
    ):
        NewsScriptDialogueLine(
            character=NewsScriptCharacter.TSUN,
            emotion=NewsScriptEmotion.CELEBRATORY,
            intensity=4,
            break_character=False,
            text="   ",
        )


@pytest.mark.parametrize(
    ("character", "emotion"),
    [
        (NewsScriptCharacter.AN, NewsScriptEmotion.ECSTATIC),
        (NewsScriptCharacter.TSUN, NewsScriptEmotion.ECSTATIC),
        (NewsScriptCharacter.JAN, NewsScriptEmotion.CELEBRATORY),
        (NewsScriptCharacter.JAN, NewsScriptEmotion.CRITICAL),
    ],
)
def test_break_character_is_only_valid_for_ecstatic_jan(
    character: NewsScriptCharacter,
    emotion: NewsScriptEmotion,
) -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="break_character is only valid for Jan in ecstatic mode",
    ):
        NewsScriptDialogueLine(
            character=character,
            emotion=emotion,
            intensity=5,
            break_character=True,
            text="うおおおお!",
        )


def test_ecstatic_jan_can_break_character() -> None:
    line = NewsScriptDialogueLine(
        character=NewsScriptCharacter.JAN,
        emotion=NewsScriptEmotion.ECSTATIC,
        intensity=5,
        break_character=True,
        text="うおおおお!勝ったあああ!!",
    )

    assert line.character is NewsScriptCharacter.JAN
    assert line.emotion is NewsScriptEmotion.ECSTATIC
    assert line.intensity == 5
    assert line.break_character is True


def test_generated_script_can_store_character_dialogue() -> None:
    dialogue = (
        NewsScriptDialogueLine(
            character=NewsScriptCharacter.JAN,
            emotion=NewsScriptEmotion.CRITICAL,
            intensity=4,
            break_character=False,
            text="いや、これはさすがに同じミス多すぎるわ。",
        ),
        NewsScriptDialogueLine(
            character=NewsScriptCharacter.AN,
            emotion=NewsScriptEmotion.SUPPORTIVE,
            intensity=3,
            break_character=False,
            text="でも、良かったところもちゃんとあったよ。",
        ),
    )

    generation = _generating().record_generated(
        hook="また同じミス。これは気になります。",
        main_narration="巨人の試合で同じミスが続きました。",
        project_g_comment="今回はジャン寄り。繰り返している点は気になる。",
        closing="みんなはどう思いますか?",
        full_narration="完成したナレーション全文",
        evidence_snapshot=(),
        completed_at=_COMPLETED_AT,
        character_dialogue=dialogue,
    )

    assert generation.character_dialogue == dialogue


def test_character_dialogue_must_not_be_empty_when_provided() -> None:
    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="character_dialogue must not be empty when provided",
    ):
        _generating().record_generated(
            hook="hook",
            main_narration="main",
            project_g_comment="comment",
            closing="closing",
            full_narration="full",
            evidence_snapshot=(),
            completed_at=_COMPLETED_AT,
            character_dialogue=(),
        )


def test_character_dialogue_must_not_exceed_six_lines() -> None:
    dialogue = tuple(
        NewsScriptDialogueLine(
            character=NewsScriptCharacter.JAN,
            emotion=NewsScriptEmotion.NEUTRAL,
            intensity=1,
            break_character=False,
            text=f"セリフ {index}",
        )
        for index in range(7)
    )

    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="character_dialogue must not contain more than 6 lines",
    ):
        _generating().record_generated(
            hook="hook",
            main_narration="main",
            project_g_comment="comment",
            closing="closing",
            full_narration="full",
            evidence_snapshot=(),
            completed_at=_COMPLETED_AT,
            character_dialogue=dialogue,
        )
