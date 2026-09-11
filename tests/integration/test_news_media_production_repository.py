from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

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
    NewsMediaProductionStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.models import (
    NewsMediaProductionRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories.news_media_productions import (
    NewsMediaProductionAlreadyExistsError,
    NewsMediaProductionNotFoundError,
)

_SCRIPT_GENERATION_ID = UUID("2c26487d-f458-4e96-b951-f92ae88c4619")
_MEDIA_PRODUCTION_1_ID = UUID("77e9571f-054e-4350-a965-f62ae13dc64b")
_MEDIA_PRODUCTION_2_ID = UUID("2b3aa892-e1e4-48b0-b53c-18bc66003d39")
_INTAKE_ID = UUID("58a28046-9600-40e8-b88f-da1644339401")

_BASE_TIME = datetime(
    2026,
    9,
    11,
    8,
    30,
    tzinfo=UTC,
)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(
        alembic_config,
        "head",
    )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


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


def _generated_script() -> NewsScriptGeneration:
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
            generation_id=_SCRIPT_GENERATION_ID,
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


def _pending_media(
    *,
    media_production_id: UUID = _MEDIA_PRODUCTION_1_ID,
    media_version: int = 1,
) -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=media_production_id,
        script_generation_id=_SCRIPT_GENERATION_ID,
        media_version=media_version,
        created_at=_BASE_TIME + timedelta(minutes=3),
    )


def _seed_generated_script(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())
    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())
    SqlAlchemyNewsScriptGenerationRepository(session).add(_generated_script())


def test_repository_adds_and_retrieves_media_production(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)
    production = _pending_media()

    stored = repository.add(production)

    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == production
    assert repository.get_by_media_production_id(production.media_production_id) == production
    assert (
        repository.get_by_script_generation_version(
            script_generation_id=_SCRIPT_GENERATION_ID,
            media_version=1,
        )
        == production
    )


def test_repository_updates_media_production(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)

    pending = _pending_media()
    repository.add(pending)

    started_at = _BASE_TIME + timedelta(minutes=4)
    completed_at = _BASE_TIME + timedelta(minutes=5)

    failed = pending.start(
        started_at=started_at,
    ).mark_failed(
        reason="renderer unavailable",
        completed_at=completed_at,
    )

    stored = repository.update(failed)

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_media_production_id(failed.media_production_id)

    assert stored.status is NewsMediaProductionStatus.FAILED
    assert stored.attempt_count == 1
    assert stored.failure_reason == "renderer unavailable"
    assert stored.started_at == started_at
    assert stored.completed_at == completed_at
    assert loaded == failed


def test_repository_rejects_duplicate_script_version(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)

    repository.add(
        _pending_media(
            media_production_id=_MEDIA_PRODUCTION_1_ID,
            media_version=1,
        )
    )

    with pytest.raises(NewsMediaProductionAlreadyExistsError):
        repository.add(
            _pending_media(
                media_production_id=_MEDIA_PRODUCTION_2_ID,
                media_version=1,
            )
        )


def test_repository_allows_new_media_version(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)

    version_1 = _pending_media(
        media_production_id=_MEDIA_PRODUCTION_1_ID,
        media_version=1,
    )
    version_2 = _pending_media(
        media_production_id=_MEDIA_PRODUCTION_2_ID,
        media_version=2,
    )

    repository.add(version_1)
    repository.add(version_2)

    assert (
        repository.get_by_script_generation_version(
            script_generation_id=_SCRIPT_GENERATION_ID,
            media_version=1,
        )
        == version_1
    )
    assert (
        repository.get_by_script_generation_version(
            script_generation_id=_SCRIPT_GENERATION_ID,
            media_version=2,
        )
        == version_2
    )


def test_repository_update_rejects_unknown_production(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)

    with pytest.raises(NewsMediaProductionNotFoundError):
        repository.update(_pending_media(media_production_id=uuid4()))


def test_database_unique_constraint_blocks_duplicate(
    migrated_session: Session,
) -> None:
    _seed_generated_script(migrated_session)

    repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)

    repository.add(
        _pending_media(
            media_production_id=_MEDIA_PRODUCTION_1_ID,
            media_version=1,
        )
    )
    migrated_session.commit()

    duplicate = _pending_media(
        media_production_id=_MEDIA_PRODUCTION_2_ID,
        media_version=1,
    )

    migrated_session.add(NewsMediaProductionRecord.from_domain(duplicate))

    with pytest.raises(IntegrityError):
        migrated_session.flush()

    migrated_session.rollback()
