from datetime import UTC, datetime, timedelta
from uuid import UUID

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.base import Base
from project_g.infrastructure.database.models.news_script_generation import (
    NewsScriptGenerationRecord,
)

_GENERATION_ID = UUID("4dd6a5cf-e8ab-42a3-a61d-6e381ddcd229")
_INTAKE_ID = UUID("81b622fb-a080-461c-b828-f635a9642185")

_CREATED_AT = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)


def _pending() -> NewsScriptGeneration:
    return NewsScriptGeneration.pending(
        generation_id=_GENERATION_ID,
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=91,
        created_at=_CREATED_AT,
    )


def test_news_script_generations_table_is_registered() -> None:
    assert "news_script_generations" in Base.metadata.tables


def test_pending_generation_record_round_trip() -> None:
    generation = _pending()

    record = NewsScriptGenerationRecord.from_domain(generation)

    assert record.generation_id == generation.generation_id
    assert record.intake_id == generation.intake_id
    assert record.generation_version == 1
    assert record.status == "pending"
    assert record.ranking_score == 91
    assert record.evidence_snapshot is None
    assert record.to_domain() == generation


def test_generated_generation_record_round_trip() -> None:
    evidence = (
        NewsScriptEvidenceSnapshot(
            text="則本はファーム戦で6回4失点だった。",
            source_id="npb_official",
            source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            competition_level=CompetitionLevel.FARM,
            role=EvidenceRole.TARGET,
        ),
    )

    generation = (
        _pending()
        .start(
            started_at=_STARTED_AT,
        )
        .record_generated(
            hook="則本昂大が1軍に合流。",
            main_narration="巨人の則本昂大投手が1軍に合流しました。",
            project_g_comment="内容は手放しで安心できるもんやないな。",
            closing="今後の起用に注目です。",
            full_narration="完成したナレーション全文",
            evidence_snapshot=evidence,
            completed_at=_COMPLETED_AT,
        )
    )

    record = NewsScriptGenerationRecord.from_domain(generation)

    assert record.status == "generated"
    assert record.evidence_snapshot == [
        {
            "text": "則本はファーム戦で6回4失点だった。",
            "source_id": "npb_official",
            "source_url": ("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            "competition_level": "farm",
            "role": "target",
        }
    ]
    assert record.to_domain() == generation


def test_empty_evidence_snapshot_round_trip() -> None:
    generation = (
        _pending()
        .start(
            started_at=_STARTED_AT,
        )
        .record_generated(
            hook="hook",
            main_narration="main",
            project_g_comment="comment",
            closing="closing",
            full_narration="full",
            evidence_snapshot=(),
            completed_at=_COMPLETED_AT,
        )
    )

    record = NewsScriptGenerationRecord.from_domain(generation)

    assert record.evidence_snapshot == []
    assert record.to_domain() == generation
