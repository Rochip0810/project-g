from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.interfaces.workers import jobs

_BASE_TIME = datetime(
    2026,
    9,
    11,
    8,
    30,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("58a28046-9600-40e8-b88f-da1644339401")
_GENERATION_ID = UUID("2c26487d-f458-4e96-b951-f92ae88c4619")


class FakeSettings:
    pass


def _source() -> NewsSource:
    return NewsSource(
        source_id="giants_official_news",
        name="Giants Official News",
        source_type=SourceType.WEBSITE,
        base_url="https://www.giants.jp/news/",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=100,
    )


def _intake() -> ManualNewsIntake:
    url = "https://www.giants.jp/news/99999/"

    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=url,
        canonical_url=url,
        submitted_at=_BASE_TIME,
    )


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
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=91,
            created_at=_BASE_TIME,
        )
        .start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
        .record_generated(
            hook="則本昂大が1軍に合流。",
            main_narration=("巨人の則本昂大投手が1軍に合流しました。"),
            project_g_comment=("内容は手放しで安心できるもんやないな。"),
            closing="今後の起用に注目です。",
            full_narration="完成したナレーション全文",
            evidence_snapshot=evidence,
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
    )


def _seed(
    engine: Engine,
) -> NewsScriptGeneration:
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    generation = _generated()

    with factory.begin() as session:
        SqlAlchemyNewsSourceRepository(session).add(_source())
        SqlAlchemyManualNewsIntakeRepository(session).add(_intake())
        SqlAlchemyNewsScriptGenerationRepository(session).add(generation)

    return generation


def _patch_database(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
) -> None:
    def create_engine(_: object) -> Engine:
        return engine

    monkeypatch.setattr(
        jobs,
        "Settings",
        FakeSettings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        create_engine,
    )


def test_worker_creates_pending_media_and_is_idempotent(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    generation_before = _seed(database_engine)

    _patch_database(
        monkeypatch,
        database_engine,
    )

    first = jobs.create_news_media_production_intakes(
        limit=5,
        media_version=1,
    )
    second = jobs.create_news_media_production_intakes(
        limit=5,
        media_version=1,
    )

    assert first["status"] == "processed"
    assert first["candidate_count"] == 1
    assert first["created_count"] == 1
    assert first["duplicate_count"] == 0

    assert second["candidate_count"] == 0
    assert second["created_count"] == 0

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_script_generation_version(
            script_generation_id=_GENERATION_ID,
            media_version=1,
        )

        generation_after = SqlAlchemyNewsScriptGenerationRepository(session).get_by_generation_id(
            _GENERATION_ID
        )

    assert media is not None
    assert media.status.value == "pending"
    assert media.attempt_count == 0
    assert generation_after == generation_before


def test_worker_db_failure_does_not_mutate_script_generation(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    generation_before = _seed(database_engine)

    _patch_database(
        monkeypatch,
        database_engine,
    )

    def fail_add(
        self: SqlAlchemyNewsMediaProductionRepository,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        raise RuntimeError("media database write failed")

    monkeypatch.setattr(
        SqlAlchemyNewsMediaProductionRepository,
        "add",
        fail_add,
    )

    with pytest.raises(
        RuntimeError,
        match="media database write failed",
    ):
        jobs.create_news_media_production_intakes(
            limit=5,
            media_version=1,
        )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        generation_after = SqlAlchemyNewsScriptGenerationRepository(session).get_by_generation_id(
            _GENERATION_ID
        )

        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_script_generation_version(
            script_generation_id=_GENERATION_ID,
            media_version=1,
        )

    assert generation_after == generation_before
    assert media is None


@pytest.mark.parametrize(
    ("limit", "media_version"),
    (
        (0, 1),
        (51, 1),
        (5, 0),
    ),
)
def test_worker_rejects_invalid_options_before_database_setup(
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    media_version: int,
) -> None:
    def unexpected_settings() -> FakeSettings:
        raise AssertionError("Settings must not be constructed")

    monkeypatch.setattr(
        jobs,
        "Settings",
        unexpected_settings,
    )

    with pytest.raises(ValueError):
        jobs.create_news_media_production_intakes(
            limit=limit,
            media_version=media_version,
        )
