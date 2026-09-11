from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.create_media_production_intakes import (
    CreateMediaProductionIntakes,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.ports.repositories.news_media_productions import (
    NewsMediaProductionAlreadyExistsError,
)

_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

_GENERATION_ID = UUID("2c26487d-f458-4e96-b951-f92ae88c4619")
_MEDIA_ID = UUID("77e9571f-054e-4350-a965-f62ae13dc64b")


def _generated() -> NewsScriptGeneration:
    evidence = (
        NewsScriptEvidenceSnapshot(
            text="則本はファーム戦で6回4失点だった。",
            source_id="npb_official",
            source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            competition_level=CompetitionLevel.FARM,
            role=EvidenceRole.TARGET,
        ),
    )

    return (
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_ID,
            intake_id=UUID("58a28046-9600-40e8-b88f-da1644339401"),
            generation_version=1,
            ranking_score=91,
            created_at=_NOW,
        )
        .start(started_at=_NOW + timedelta(minutes=1))
        .record_generated(
            hook="則本昂大が1軍に合流。",
            main_narration=("巨人の則本昂大投手が1軍に合流しました。"),
            project_g_comment=("内容は手放しで安心できるもんやないな。"),
            closing="今後の起用に注目です。",
            full_narration="完成したナレーション全文",
            evidence_snapshot=evidence,
            completed_at=_NOW + timedelta(minutes=2),
        )
    )


class FakeCandidateRepository:
    def __init__(
        self,
        candidates: tuple[NewsScriptGeneration, ...],
    ) -> None:
        self.candidates = candidates
        self.calls: list[tuple[int, int]] = []

    def list_candidates(
        self,
        *,
        media_version: int,
        limit: int,
    ) -> tuple[NewsScriptGeneration, ...]:
        self.calls.append((media_version, limit))
        return self.candidates


class FakeMediaRepository:
    def __init__(
        self,
        *,
        duplicate: bool = False,
    ) -> None:
        self.duplicate = duplicate
        self.added: list[NewsMediaProduction] = []

    def add(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        if self.duplicate:
            raise NewsMediaProductionAlreadyExistsError(
                production.script_generation_id,
                production.media_version,
            )

        self.added.append(production)
        return production

    def update(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        raise AssertionError("not used")

    def get_by_media_production_id(
        self,
        media_production_id: UUID,
    ) -> NewsMediaProduction | None:
        raise AssertionError("not used")

    def get_by_script_generation_version(
        self,
        *,
        script_generation_id: UUID,
        media_version: int,
    ) -> NewsMediaProduction | None:
        raise AssertionError("not used")


def test_generated_script_creates_pending_media_production() -> None:
    candidate_repository = FakeCandidateRepository((_generated(),))
    media_repository = FakeMediaRepository()

    service = CreateMediaProductionIntakes(
        candidate_repository=candidate_repository,
        media_repository=media_repository,
        id_factory=lambda: _MEDIA_ID,
    )

    result = service.execute(
        media_version=1,
        limit=5,
        created_at=_NOW + timedelta(minutes=3),
    )

    assert candidate_repository.calls == [(1, 5)]
    assert result.candidate_count == 1
    assert result.created_count == 1
    assert result.duplicate_count == 0
    assert len(result.created) == 1

    production = result.created[0]

    assert production.media_production_id == _MEDIA_ID
    assert production.script_generation_id == _GENERATION_ID
    assert production.media_version == 1
    assert production.status.value == "pending"
    assert production.attempt_count == 0


def test_duplicate_media_production_is_safe() -> None:
    candidate_repository = FakeCandidateRepository((_generated(),))
    media_repository = FakeMediaRepository(duplicate=True)

    service = CreateMediaProductionIntakes(
        candidate_repository=candidate_repository,
        media_repository=media_repository,
        id_factory=lambda: _MEDIA_ID,
    )

    result = service.execute(
        media_version=1,
        limit=5,
        created_at=_NOW + timedelta(minutes=3),
    )

    assert result.candidate_count == 1
    assert result.created_count == 0
    assert result.duplicate_count == 1
    assert result.created == ()


@pytest.mark.parametrize(
    ("media_version", "limit"),
    [
        (0, 5),
        (1, 0),
        (1, 51),
    ],
)
def test_invalid_options_are_rejected(
    media_version: int,
    limit: int,
) -> None:
    service = CreateMediaProductionIntakes(
        candidate_repository=FakeCandidateRepository(()),
        media_repository=FakeMediaRepository(),
    )

    with pytest.raises(ValueError):
        service.execute(
            media_version=media_version,
            limit=limit,
            created_at=_NOW,
        )


def test_naive_created_at_is_rejected() -> None:
    service = CreateMediaProductionIntakes(
        candidate_repository=FakeCandidateRepository(()),
        media_repository=FakeMediaRepository(),
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        service.execute(
            media_version=1,
            limit=5,
            created_at=datetime(2026, 9, 11, 12, 0),
        )
