from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
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
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.models import (
    NewsScriptGenerationRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaIntakeCandidateRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)

_BASE_TIME = datetime(
    2026,
    9,
    11,
    8,
    30,
    tzinfo=UTC,
)

_INTAKE_IDS = tuple(
    UUID(value)
    for value in (
        "58a28046-9600-40e8-b88f-da1644339401",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a001",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a002",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a003",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a004",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a005",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a006",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a007",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a008",
        "c6c0ee54-267d-4e2f-8f22-f97cc002a009",
    )
)

_GENERATION_IDS = tuple(
    UUID(value)
    for value in (
        "2c26487d-f458-4e96-b951-f92ae88c4619",
        "82fe92bb-ee37-409f-b27e-d6a134de5944",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112001",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112002",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112003",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112004",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112005",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112006",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112007",
        "1c7aa3d8-d0f9-45a9-9245-9bf1db112008",
    )
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


def _intake(
    *,
    index: int,
) -> ManualNewsIntake:
    intake_id = _INTAKE_IDS[index]
    url = f"https://www.giants.jp/news/{90000 + index}/"

    return ManualNewsIntake(
        intake_id=intake_id,
        source_id="giants_official_news",
        submitted_url=url,
        canonical_url=url,
        submitted_at=_BASE_TIME + timedelta(seconds=index),
    )


def _seed_intakes(
    session: Session,
    *,
    count: int,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())

    repository = SqlAlchemyManualNewsIntakeRepository(session)

    for index in range(count):
        repository.add(_intake(index=index))


def _evidence() -> tuple[NewsScriptEvidenceSnapshot, ...]:
    return (
        NewsScriptEvidenceSnapshot(
            text="則本はファーム戦で6回4失点だった。",
            source_id="npb_official",
            source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            competition_level=CompetitionLevel.FARM,
            role=EvidenceRole.TARGET,
        ),
    )


def _generated(
    *,
    index: int,
    completed_offset_minutes: int,
) -> NewsScriptGeneration:
    created_at = _BASE_TIME + timedelta(seconds=index)
    started_at = created_at + timedelta(minutes=1)
    completed_at = _BASE_TIME + timedelta(minutes=completed_offset_minutes)

    return (
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_IDS[index],
            intake_id=_INTAKE_IDS[index],
            generation_version=1,
            ranking_score=91,
            created_at=created_at,
        )
        .start(
            started_at=started_at,
        )
        .record_generated(
            hook=f"フック {index}",
            main_narration=f"本文 {index}",
            project_g_comment=f"コメント {index}",
            closing=f"締め {index}",
            full_narration=f"全文 {index}",
            evidence_snapshot=_evidence(),
            completed_at=completed_at,
        )
    )


def test_candidate_repository_filters_ineligible_states_and_existing_media(
    migrated_session: Session,
) -> None:
    _seed_intakes(
        migrated_session,
        count=6,
    )

    script_repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    eligible = _generated(
        index=0,
        completed_offset_minutes=10,
    )
    script_repository.add(eligible)

    pending = NewsScriptGeneration.pending(
        generation_id=_GENERATION_IDS[1],
        intake_id=_INTAKE_IDS[1],
        generation_version=1,
        ranking_score=90,
        created_at=_BASE_TIME,
    )
    script_repository.add(pending)

    generating = NewsScriptGeneration.pending(
        generation_id=_GENERATION_IDS[2],
        intake_id=_INTAKE_IDS[2],
        generation_version=1,
        ranking_score=89,
        created_at=_BASE_TIME,
    ).start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    )
    script_repository.add(generating)

    failed = (
        NewsScriptGeneration.pending(
            generation_id=_GENERATION_IDS[3],
            intake_id=_INTAKE_IDS[3],
            generation_version=1,
            ranking_score=88,
            created_at=_BASE_TIME,
        )
        .start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
        .mark_failed(
            reason="generation failed",
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
    )
    script_repository.add(failed)

    existing_media_script = _generated(
        index=4,
        completed_offset_minutes=11,
    )
    script_repository.add(existing_media_script)

    SqlAlchemyNewsMediaProductionRepository(migrated_session).add(
        NewsMediaProduction.pending(
            media_production_id=UUID("77e9571f-054e-4350-a965-f62ae13dc64b"),
            script_generation_id=(existing_media_script.generation_id),
            media_version=1,
            created_at=_BASE_TIME + timedelta(minutes=12),
        )
    )

    incomplete_record = NewsScriptGenerationRecord(
        generation_id=_GENERATION_IDS[5],
        intake_id=_INTAKE_IDS[5],
        generation_version=1,
        status="generated",
        ranking_score=87,
        attempt_count=1,
        failure_reason=None,
        hook="",
        main_narration="本文",
        project_g_comment="コメント",
        closing="締め",
        full_narration="全文",
        evidence_snapshot=[
            {
                "text": "証拠",
                "source_id": "npb_official",
                "source_url": "https://npb.jp/",
                "competition_level": "farm",
                "role": "target",
            }
        ],
        created_at=_BASE_TIME,
        started_at=_BASE_TIME + timedelta(minutes=1),
        completed_at=_BASE_TIME + timedelta(minutes=3),
        updated_at=_BASE_TIME + timedelta(minutes=3),
    )
    migrated_session.add(incomplete_record)
    migrated_session.flush()

    repository = SqlAlchemyNewsMediaIntakeCandidateRepository(migrated_session)

    candidates = repository.list_candidates(
        media_version=1,
        limit=5,
    )

    assert tuple(item.generation_id for item in candidates) == (eligible.generation_id,)


def test_existing_media_version_only_blocks_same_version(
    migrated_session: Session,
) -> None:
    _seed_intakes(
        migrated_session,
        count=1,
    )

    generated = _generated(
        index=0,
        completed_offset_minutes=10,
    )

    SqlAlchemyNewsScriptGenerationRepository(migrated_session).add(generated)

    SqlAlchemyNewsMediaProductionRepository(migrated_session).add(
        NewsMediaProduction.pending(
            media_production_id=UUID("77e9571f-054e-4350-a965-f62ae13dc64b"),
            script_generation_id=generated.generation_id,
            media_version=1,
            created_at=_BASE_TIME + timedelta(minutes=11),
        )
    )

    repository = SqlAlchemyNewsMediaIntakeCandidateRepository(migrated_session)

    version_1 = repository.list_candidates(
        media_version=1,
        limit=5,
    )
    version_2 = repository.list_candidates(
        media_version=2,
        limit=5,
    )

    assert version_1 == ()
    assert tuple(item.generation_id for item in version_2) == (generated.generation_id,)


def test_candidate_repository_applies_deterministic_limit(
    migrated_session: Session,
) -> None:
    _seed_intakes(
        migrated_session,
        count=7,
    )

    script_repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    generations = tuple(
        _generated(
            index=index,
            completed_offset_minutes=10 + index,
        )
        for index in range(7)
    )

    for generation in generations:
        script_repository.add(generation)

    repository = SqlAlchemyNewsMediaIntakeCandidateRepository(migrated_session)

    candidates = repository.list_candidates(
        media_version=1,
        limit=5,
    )

    assert len(candidates) == 5
    assert tuple(item.generation_id for item in candidates) == tuple(
        generation.generation_id for generation in generations[:5]
    )


def test_candidate_repository_skips_invalid_generated_before_limit(
    migrated_session: Session,
) -> None:
    _seed_intakes(
        migrated_session,
        count=2,
    )

    invalid_record = NewsScriptGenerationRecord(
        generation_id=_GENERATION_IDS[0],
        intake_id=_INTAKE_IDS[0],
        generation_version=1,
        status="generated",
        ranking_score=92,
        attempt_count=1,
        failure_reason=None,
        hook="フック invalid",
        main_narration="本文 invalid",
        project_g_comment="コメント invalid",
        closing="締め invalid",
        full_narration="全文 invalid",
        evidence_snapshot=[
            {
                "text": " ",
                "source_id": "npb_official",
                "source_url": "https://npb.jp/",
                "competition_level": "farm",
                "role": "target",
            }
        ],
        created_at=_BASE_TIME,
        started_at=_BASE_TIME + timedelta(minutes=1),
        completed_at=_BASE_TIME + timedelta(minutes=2),
        updated_at=_BASE_TIME + timedelta(minutes=2),
    )

    migrated_session.add(invalid_record)
    migrated_session.flush()

    valid = _generated(
        index=1,
        completed_offset_minutes=3,
    )

    SqlAlchemyNewsScriptGenerationRepository(migrated_session).add(valid)

    repository = SqlAlchemyNewsMediaIntakeCandidateRepository(migrated_session)

    candidates = repository.list_candidates(
        media_version=1,
        limit=1,
    )

    assert tuple(item.generation_id for item in candidates) == (valid.generation_id,)
