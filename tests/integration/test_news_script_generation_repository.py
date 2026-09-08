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
from project_g.domain.news.script_generation import (
    InvalidNewsScriptGenerationError,
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    NewsScriptGenerationAlreadyExistsError,
    NewsScriptGenerationNotFoundError,
)

_GENERATION_1_ID = UUID("2c26487d-f458-4e96-b951-f92ae88c4619")
_GENERATION_2_ID = UUID("82fe92bb-ee37-409f-b27e-d6a134de5944")
_INTAKE_ID = UUID("58a28046-9600-40e8-b88f-da1644339401")

_BASE_TIME = datetime(
    2026,
    9,
    6,
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


def _seed_intake(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())

    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())


def _pending(
    *,
    generation_id: UUID = _GENERATION_1_ID,
    generation_version: int = 1,
    ranking_score: int = 91,
) -> NewsScriptGeneration:
    return NewsScriptGeneration.pending(
        generation_id=generation_id,
        intake_id=_INTAKE_ID,
        generation_version=generation_version,
        ranking_score=ranking_score,
        created_at=_BASE_TIME,
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
        _pending()
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


def test_repository_adds_and_retrieves_generation(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)
    generation = _pending()

    stored = repository.add(generation)

    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == generation
    assert repository.get_by_generation_id(generation.generation_id) == generation
    assert (
        repository.get_by_intake_version(
            intake_id=_INTAKE_ID,
            generation_version=1,
        )
        == generation
    )


def test_repository_updates_generated_output(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    pending = _pending()
    repository.add(pending)

    generated = _generated()
    stored = repository.update(generated)

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_generation_id(generated.generation_id)

    assert stored.status is (NewsScriptGenerationStatus.GENERATED)
    assert stored.ranking_score == 91
    assert stored.evidence_snapshot is not None
    assert len(stored.evidence_snapshot) == 1
    assert loaded == generated


def test_repository_rejects_duplicate_intake_version(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(
        _pending(
            generation_id=_GENERATION_1_ID,
            generation_version=1,
        )
    )

    with pytest.raises(NewsScriptGenerationAlreadyExistsError):
        repository.add(
            _pending(
                generation_id=_GENERATION_2_ID,
                generation_version=1,
            )
        )


def test_repository_allows_new_generation_version(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    version_1 = _pending(
        generation_id=_GENERATION_1_ID,
        generation_version=1,
        ranking_score=91,
    )
    version_2 = _pending(
        generation_id=_GENERATION_2_ID,
        generation_version=2,
        ranking_score=88,
    )

    repository.add(version_1)
    repository.add(version_2)

    assert (
        repository.get_by_intake_version(
            intake_id=_INTAKE_ID,
            generation_version=1,
        )
        == version_1
    )
    assert (
        repository.get_by_intake_version(
            intake_id=_INTAKE_ID,
            generation_version=2,
        )
        == version_2
    )


def test_repository_update_rejects_unknown_generation(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    with pytest.raises(NewsScriptGenerationNotFoundError):
        repository.update(_pending())


def test_repository_atomically_claims_pending_generation(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    pending = _pending()
    repository.add(pending)
    migrated_session.commit()

    started_at = _BASE_TIME + timedelta(minutes=1)

    claimed = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=started_at,
    )

    migrated_session.commit()

    assert claimed is not None
    assert claimed.status is (NewsScriptGenerationStatus.GENERATING)
    assert claimed.attempt_count == 1
    assert claimed.ranking_score == 91
    assert claimed.started_at == started_at
    assert claimed.completed_at is None
    assert claimed.failure_reason is None


def test_repository_second_claim_is_rejected(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(_pending())
    migrated_session.commit()

    first = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=_BASE_TIME + timedelta(minutes=1),
    )
    migrated_session.commit()

    second = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=_BASE_TIME + timedelta(minutes=2),
    )

    assert first is not None
    assert second is None


def test_repository_failed_generation_can_be_claimed_for_retry(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    pending = _pending()

    failed = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    ).mark_failed(
        reason="OpenAI request failed",
        completed_at=_BASE_TIME + timedelta(minutes=2),
    )

    repository.add(failed)
    migrated_session.commit()

    retry_started_at = _BASE_TIME + timedelta(minutes=3)

    claimed = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=retry_started_at,
    )

    migrated_session.commit()

    assert claimed is not None
    assert claimed.status is (NewsScriptGenerationStatus.GENERATING)
    assert claimed.attempt_count == 2
    assert claimed.failure_reason is None
    assert claimed.started_at == retry_started_at
    assert claimed.completed_at is None


def test_repository_generated_generation_cannot_be_claimed(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(_generated())
    migrated_session.commit()

    claimed = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=_BASE_TIME + timedelta(minutes=10),
    )

    assert claimed is None


def test_repository_claim_rejects_naive_started_at(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(_pending())

    with pytest.raises(
        InvalidNewsScriptGenerationError,
        match="started_at must be timezone-aware",
    ):
        repository.claim_by_intake_version(
            intake_id=_INTAKE_ID,
            generation_version=1,
            started_at=datetime(
                2026,
                9,
                6,
                8,
                31,
            ),
        )


def test_repository_fresh_generating_generation_is_not_reclaimed(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(_pending())
    migrated_session.commit()

    first_started_at = _BASE_TIME + timedelta(minutes=1)

    first = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=first_started_at,
    )
    migrated_session.commit()

    second = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        stale_before=_BASE_TIME,
    )

    assert first is not None
    assert first.status is (NewsScriptGenerationStatus.GENERATING)
    assert second is None


def test_repository_atomically_reclaims_stale_generating_generation(
    migrated_session: Session,
) -> None:
    _seed_intake(migrated_session)

    repository = SqlAlchemyNewsScriptGenerationRepository(migrated_session)

    repository.add(_pending())
    migrated_session.commit()

    first_started_at = _BASE_TIME + timedelta(minutes=1)

    first = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=first_started_at,
    )
    migrated_session.commit()

    stale_before = _BASE_TIME + timedelta(minutes=6)
    reclaim_started_at = _BASE_TIME + timedelta(minutes=12)

    reclaimed = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=reclaim_started_at,
        stale_before=stale_before,
    )
    migrated_session.commit()

    competing_claim = repository.claim_by_intake_version(
        intake_id=_INTAKE_ID,
        generation_version=1,
        started_at=_BASE_TIME + timedelta(minutes=13),
        stale_before=stale_before,
    )

    assert first is not None
    assert reclaimed is not None

    assert reclaimed.status is (NewsScriptGenerationStatus.GENERATING)
    assert reclaimed.attempt_count == 2
    assert reclaimed.started_at == reclaim_started_at
    assert reclaimed.completed_at is None
    assert reclaimed.failure_reason is None

    assert competing_claim is None
