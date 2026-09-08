from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.generate_news_script import (
    GenerateNewsScriptResult,
)
from project_g.application.news.manage_news_script_generation import (
    ManageNewsScriptGeneration,
    NewsScriptGenerationRankingScoreMismatchError,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)
from project_g.ports.news_script import (
    NewsScriptBackgroundFact,
    NewsScriptGeneratorResult,
)
from project_g.ports.repositories.news_script_generations import (
    NewsScriptGenerationAlreadyExistsError,
)

_GENERATION_ID = UUID("a10ea424-c1c0-4759-8558-740412e6fd9a")
_INTAKE_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")

_CREATED_AT = datetime(
    2026,
    9,
    6,
    9,
    0,
    tzinfo=UTC,
)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=2)


class FakeRepository:
    def __init__(self) -> None:
        self.generation: NewsScriptGeneration | None = None
        self.add_calls = 0
        self.raise_duplicate_on_add = False
        self.claim_started_at: datetime | None = None
        self.claim_stale_before: datetime | None = None

    def add(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        self.add_calls += 1

        if self.raise_duplicate_on_add:
            raise NewsScriptGenerationAlreadyExistsError(
                generation.intake_id,
                generation.generation_version,
            )

        self.generation = generation
        return generation

    def update(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        self.generation = generation
        return generation

    def get_by_generation_id(
        self,
        generation_id: UUID,
    ) -> NewsScriptGeneration | None:
        if self.generation is not None and self.generation.generation_id == generation_id:
            return self.generation

        return None

    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None:
        if (
            self.generation is not None
            and self.generation.intake_id == intake_id
            and self.generation.generation_version == generation_version
        ):
            return self.generation

        return None

    def claim_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsScriptGeneration | None:
        self.claim_started_at = started_at
        self.claim_stale_before = stale_before

        generation = self.get_by_intake_version(
            intake_id=intake_id,
            generation_version=generation_version,
        )

        if generation is None:
            return None

        if generation.status not in {
            NewsScriptGenerationStatus.PENDING,
            NewsScriptGenerationStatus.FAILED,
        }:
            return None

        claimed = generation.start(
            started_at=started_at,
        )
        self.generation = claimed
        return claimed


def _manager(
    repository: FakeRepository,
) -> ManageNewsScriptGeneration:
    return ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _CREATED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )


def _pending(
    *,
    ranking_score: int = 87,
) -> NewsScriptGeneration:
    return NewsScriptGeneration.pending(
        generation_id=_GENERATION_ID,
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=ranking_score,
        created_at=_CREATED_AT,
    )


def _result() -> GenerateNewsScriptResult:
    fact = NewsScriptBackgroundFact(
        text=(
            "2026年8月15日のファーム戦で則本は勝投手となり、"
            "6回、84球、被安打9、被本塁打1、四球0、"
            "奪三振3、4失点(自責3)だった。"
        ),
        source_id="npb_official",
        source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.TARGET,
    )

    script = NewsScriptGeneratorResult(
        hook="則本が1軍に合流。",
        main_narration="巨人の則本昂大投手が1軍に合流しました。",
        project_g_comment=("内容は手放しで安心できるもんやないな。"),
        closing="今後の起用に注目です。",
        full_narration="完成したナレーション全文",
        evidence_points=(),
    )

    return GenerateNewsScriptResult(
        script=script,
        background_facts=(fact,),
    )


def test_prepare_creates_pending_generation() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    generation = manager.prepare(
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=87,
    )

    assert generation.status is (NewsScriptGenerationStatus.PENDING)
    assert generation.generation_id == _GENERATION_ID
    assert generation.intake_id == _INTAKE_ID
    assert generation.generation_version == 1
    assert generation.ranking_score == 87
    assert repository.add_calls == 1


def test_prepare_returns_existing_generation() -> None:
    repository = FakeRepository()
    repository.generation = _pending()

    manager = _manager(repository)

    generation = manager.prepare(
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=87,
    )

    assert generation == repository.generation
    assert repository.add_calls == 0


def test_prepare_rejects_ranking_score_mismatch() -> None:
    repository = FakeRepository()
    repository.generation = _pending(
        ranking_score=87,
    )

    manager = _manager(repository)

    with pytest.raises(NewsScriptGenerationRankingScoreMismatchError):
        manager.prepare(
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=91,
        )

    assert repository.generation.ranking_score == 87


def test_prepare_handles_concurrent_duplicate_creation() -> None:
    repository = FakeRepository()
    repository.raise_duplicate_on_add = True

    existing = _pending()

    original_add = repository.add

    def racing_add(
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        repository.generation = existing
        return original_add(generation)

    repository.add = racing_add  # type: ignore[method-assign]

    manager = _manager(repository)

    generation = manager.prepare(
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=87,
    )

    assert generation == existing


def test_claim_uses_atomic_repository_claim() -> None:
    repository = FakeRepository()
    repository.generation = _pending()

    manager = ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _STARTED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )

    claimed = manager.claim(
        intake_id=_INTAKE_ID,
        generation_version=1,
    )

    assert claimed is not None
    assert claimed.status is (NewsScriptGenerationStatus.GENERATING)
    assert claimed.attempt_count == 1
    assert claimed.started_at == _STARTED_AT
    assert claimed.ranking_score == 87
    assert repository.claim_started_at == _STARTED_AT
    assert repository.claim_stale_before is None


def test_record_generated_persists_script_and_evidence() -> None:
    repository = FakeRepository()
    repository.generation = _pending().start(started_at=_STARTED_AT)

    manager = ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _COMPLETED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )

    generated = manager.record_generated(
        generation_id=_GENERATION_ID,
        result=_result(),
    )

    assert generated.status is (NewsScriptGenerationStatus.GENERATED)
    assert generated.ranking_score == 87
    assert generated.hook == "則本が1軍に合流。"
    assert generated.evidence_snapshot is not None
    assert len(generated.evidence_snapshot) == 1

    evidence = generated.evidence_snapshot[0]

    assert evidence.source_id == "npb_official"
    assert evidence.competition_level is (CompetitionLevel.FARM)
    assert evidence.role is EvidenceRole.TARGET


def test_mark_failed_preserves_ranking_score() -> None:
    repository = FakeRepository()
    repository.generation = _pending().start(started_at=_STARTED_AT)

    manager = ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _COMPLETED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )

    failed = manager.mark_failed(
        generation_id=_GENERATION_ID,
        reason="OpenAI request failed",
    )

    assert failed.status is (NewsScriptGenerationStatus.FAILED)
    assert failed.ranking_score == 87
    assert failed.failure_reason == "OpenAI request failed"
    assert failed.completed_at == _COMPLETED_AT


def test_claim_computes_stale_cutoff_from_timeout() -> None:
    repository = FakeRepository()
    repository.generation = _pending()

    manager = ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _STARTED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )

    claimed = manager.claim(
        intake_id=_INTAKE_ID,
        generation_version=1,
        stale_after_seconds=300,
    )

    assert claimed is not None
    assert repository.claim_started_at == _STARTED_AT
    assert repository.claim_stale_before == (_STARTED_AT - timedelta(seconds=300))


def test_claim_rejects_invalid_stale_timeout() -> None:
    repository = FakeRepository()
    repository.generation = _pending()

    manager = ManageNewsScriptGeneration(
        repository=repository,
        clock=lambda: _STARTED_AT,
        generation_id_factory=lambda: _GENERATION_ID,
    )

    with pytest.raises(
        ValueError,
        match="stale_after_seconds must be at least 1",
    ):
        manager.claim(
            intake_id=_INTAKE_ID,
            generation_version=1,
            stale_after_seconds=0,
        )
