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
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.media_production import NewsMediaProduction
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.infrastructure.database.models import (
    NewsVideoGenerationRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemyNewsVideoGenerationRepository,
)
from project_g.ports.repositories.news_video_generations import (
    NewsVideoGenerationAlreadyExistsError,
    NewsVideoGenerationNotFoundError,
)

_SCRIPT_GENERATION_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00101")
_MEDIA_PRODUCTION_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00201")
_VIDEO_GENERATION_1_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00301")
_VIDEO_GENERATION_2_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00302")
_INTAKE_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00401")

_BASE_TIME = datetime(
    2026,
    9,
    18,
    7,
    0,
    tzinfo=UTC,
)

_SOURCE_AUDIO_HASH = "a" * 64
_CONTENT_HASH = "b" * 64


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
    url = "https://www.giants.jp/news/99997/"

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
            text="動画生成テスト用の確認済み事実。",
            source_id="npb_official",
            source_url="https://npb.jp/example/",
            competition_level=CompetitionLevel.FIRST_TEAM,
            role=EvidenceRole.TARGET,
        ),
    )

    return (
        NewsScriptGeneration.pending(
            generation_id=_SCRIPT_GENERATION_ID,
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=90,
            created_at=_BASE_TIME,
        )
        .start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
        .record_generated(
            hook="巨人の最新ニュースです。",
            main_narration="事実を伝えるナレーションです。",
            project_g_comment="ここはしっかり見たいところやな。",
            closing="今後の動きにも注目です。",
            full_narration="完成したProject Gナレーション全文",
            evidence_snapshot=evidence,
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
    )


def _pending_media() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_MEDIA_PRODUCTION_ID,
        script_generation_id=_SCRIPT_GENERATION_ID,
        media_version=1,
        created_at=_BASE_TIME + timedelta(minutes=3),
    )


def _pending_video(
    *,
    video_generation_id: UUID = _VIDEO_GENERATION_1_ID,
    video_version: int = 1,
) -> NewsVideoGeneration:
    return NewsVideoGeneration.pending(
        video_generation_id=video_generation_id,
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=video_version,
        renderer="ffmpeg",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
        source_audio_sha256=_SOURCE_AUDIO_HASH,
        created_at=_BASE_TIME + timedelta(minutes=4),
    )


def _seed_media(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())
    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())
    SqlAlchemyNewsScriptGenerationRepository(session).add(_generated_script())
    SqlAlchemyNewsMediaProductionRepository(session).add(_pending_media())


def test_repository_adds_and_retrieves_video_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)
    generation = _pending_video()

    stored = repository.add(generation)

    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == generation
    assert repository.get_by_video_generation_id(generation.video_generation_id) == generation
    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            video_version=1,
        )
        == generation
    )


def test_repository_updates_generated_video(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    pending = _pending_video()
    repository.add(pending)

    generated = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=5),
    ).record_generated(
        storage_key=(f"media/video/{_MEDIA_PRODUCTION_ID}/v1.mp4"),
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )

    stored = repository.update(generated)

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_video_generation_id(generated.video_generation_id)

    assert stored.status is NewsVideoGenerationStatus.GENERATED
    assert stored.attempt_count == 1
    assert stored.byte_size == 23456
    assert stored.content_sha256 == _CONTENT_HASH
    assert stored.duration_ms == 12345
    assert loaded == generated


def test_repository_rejects_duplicate_media_version(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(
        _pending_video(
            video_generation_id=_VIDEO_GENERATION_1_ID,
            video_version=1,
        )
    )

    with pytest.raises(NewsVideoGenerationAlreadyExistsError):
        repository.add(
            _pending_video(
                video_generation_id=_VIDEO_GENERATION_2_ID,
                video_version=1,
            )
        )


def test_repository_allows_new_video_version(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    version_1 = _pending_video(
        video_generation_id=_VIDEO_GENERATION_1_ID,
        video_version=1,
    )
    version_2 = _pending_video(
        video_generation_id=_VIDEO_GENERATION_2_ID,
        video_version=2,
    )

    repository.add(version_1)
    repository.add(version_2)

    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            video_version=1,
        )
        == version_1
    )
    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            video_version=2,
        )
        == version_2
    )


def test_repository_update_rejects_unknown_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    with pytest.raises(NewsVideoGenerationNotFoundError):
        repository.update(
            _pending_video(
                video_generation_id=uuid4(),
            )
        )


def test_database_unique_constraint_blocks_duplicate(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(
        _pending_video(
            video_generation_id=_VIDEO_GENERATION_1_ID,
            video_version=1,
        )
    )
    migrated_session.commit()

    duplicate = _pending_video(
        video_generation_id=_VIDEO_GENERATION_2_ID,
        video_version=1,
    )

    migrated_session.add(NewsVideoGenerationRecord.from_domain(duplicate))

    with pytest.raises(IntegrityError):
        migrated_session.flush()

    migrated_session.rollback()


def test_claim_atomically_starts_pending_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    started_at = _BASE_TIME + timedelta(minutes=5)

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=started_at,
    )

    assert claimed is not None
    assert claimed.status is NewsVideoGenerationStatus.GENERATING
    assert claimed.attempt_count == 1
    assert claimed.started_at == started_at
    assert claimed.updated_at == started_at


def test_claim_retries_failed_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    pending = _pending_video()
    repository.add(pending)

    failed = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=5),
    ).mark_failed(
        reason="temporary FFmpeg failure",
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )
    repository.update(failed)

    retry_at = _BASE_TIME + timedelta(minutes=7)

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=retry_at,
    )

    assert claimed is not None
    assert claimed.status is NewsVideoGenerationStatus.GENERATING
    assert claimed.attempt_count == 2
    assert claimed.failure_reason is None
    assert claimed.completed_at is None


def test_claim_reclaims_stale_generating_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    first_started_at = _BASE_TIME + timedelta(minutes=5)

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=first_started_at,
    )

    assert first_claim is not None
    assert first_claim.attempt_count == 1

    reclaimed_at = _BASE_TIME + timedelta(minutes=20)

    reclaimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=reclaimed_at,
        stale_before=_BASE_TIME + timedelta(minutes=10),
    )

    assert reclaimed is not None
    assert reclaimed.status is NewsVideoGenerationStatus.GENERATING
    assert reclaimed.attempt_count == 2
    assert reclaimed.started_at == reclaimed_at


def test_claim_does_not_take_fresh_generating_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    first_started_at = _BASE_TIME + timedelta(minutes=5)

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=first_started_at,
    )

    assert first_claim is not None

    second_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=6),
        stale_before=_BASE_TIME + timedelta(minutes=4),
    )

    assert second_claim is None
