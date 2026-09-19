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
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
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
    SqlAlchemyNewsNarrationAudioGenerationRepository,
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
_AUDIO_GENERATION_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00202")

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
_SOURCE_TEXT_HASH = "c" * 64
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


def _generated_audio() -> NewsNarrationAudioGeneration:
    generated_at = _BASE_TIME + timedelta(minutes=4)

    return (
        NewsNarrationAudioGeneration.pending(
            audio_generation_id=_AUDIO_GENERATION_ID,
            media_production_id=_MEDIA_PRODUCTION_ID,
            audio_version=1,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            source_text_sha256=_SOURCE_TEXT_HASH,
            created_at=generated_at,
        )
        .start(
            started_at=generated_at,
        )
        .record_generated(
            storage_key=f"media/audio/{_MEDIA_PRODUCTION_ID}/v1.mp3",
            byte_size=12345,
            content_sha256=_SOURCE_AUDIO_HASH,
            completed_at=generated_at,
        )
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
        source_audio_generation_id=_AUDIO_GENERATION_ID,
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
    SqlAlchemyNewsNarrationAudioGenerationRepository(session).add(_generated_audio())


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


def test_claim_rejects_unexpected_first_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    # The first attempt must be a1, not a2.
    rejected = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=2,
    )

    assert rejected is None

    pending = repository.get_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
    )

    assert pending is not None
    assert pending.status is NewsVideoGenerationStatus.PENDING
    assert pending.attempt_count == 0

    # The correct first attempt can claim the same record.
    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert claimed is not None
    assert claimed.status is NewsVideoGenerationStatus.GENERATING
    assert claimed.attempt_count == 1


def test_claim_rejects_old_job_after_failure(
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
    migrated_session.commit()

    # The old a1 job must not claim the failed generation.
    rejected = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=7),
        expected_attempt_number=1,
    )

    assert rejected is None

    current = repository.get_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
    )

    assert current is not None
    assert current.status is NewsVideoGenerationStatus.FAILED
    assert current.attempt_count == 1

    # The correct next attempt, a2, can claim the record.
    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=7),
        expected_attempt_number=2,
    )

    assert claimed is not None
    assert claimed.status is NewsVideoGenerationStatus.GENERATING
    assert claimed.attempt_count == 2
    assert claimed.failure_reason is None


def test_stale_generation_rejects_old_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert first_claim is not None
    assert first_claim.attempt_count == 1

    # a2 reclaims the stale a1 generation.
    second_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=20),
        stale_before=_BASE_TIME + timedelta(minutes=10),
        expected_attempt_number=2,
    )

    assert second_claim is not None
    assert second_claim.attempt_count == 2

    # Even if a1 arrives late, it cannot claim a new attempt.
    old_job = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=40),
        stale_before=_BASE_TIME + timedelta(minutes=30),
        expected_attempt_number=1,
    )

    assert old_job is None

    current = repository.get_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
    )

    assert current is not None
    assert current.status is NewsVideoGenerationStatus.GENERATING
    assert current.attempt_count == 2


def test_claim_rejects_invalid_expected_attempt_number(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    with pytest.raises(
        ValueError,
        match="expected_attempt_number must be at least 1",
    ):
        repository.claim_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            video_version=1,
            started_at=_BASE_TIME + timedelta(minutes=5),
            expected_attempt_number=0,
        )


def test_record_generated_if_current_succeeds(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert claimed is not None
    assert claimed.attempt_count == 1

    completed_at = _BASE_TIME + timedelta(minutes=6)

    generated = repository.record_generated_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a1.mp4",
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
        completed_at=completed_at,
    )

    assert generated is not None
    assert generated.status is NewsVideoGenerationStatus.GENERATED
    assert generated.attempt_count == 1
    assert generated.storage_key == (f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a1.mp4")
    assert generated.byte_size == 23456
    assert generated.content_sha256 == _CONTENT_HASH
    assert generated.duration_ms == 12345
    assert generated.completed_at == completed_at

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_video_generation_id(claimed.video_generation_id)

    assert loaded == generated


def test_record_generated_if_current_rejects_superseded_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert first_claim is not None
    assert first_claim.attempt_count == 1

    # a1が期限切れになり、a2が処理権限を取得する。
    second_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=20),
        stale_before=_BASE_TIME + timedelta(minutes=10),
        expected_attempt_number=2,
    )

    assert second_claim is not None
    assert second_claim.attempt_count == 2

    migrated_session.commit()

    # 古いa1が遅れて完了してもDBを更新できない。
    old_result = repository.record_generated_if_current(
        video_generation_id=first_claim.video_generation_id,
        expected_attempt_number=1,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a1.mp4",
        byte_size=12345,
        content_sha256=_CONTENT_HASH,
        duration_ms=10000,
        completed_at=_BASE_TIME + timedelta(minutes=21),
    )

    assert old_result is None

    migrated_session.expire_all()

    current = repository.get_by_video_generation_id(first_claim.video_generation_id)

    assert current is not None
    assert current.status is NewsVideoGenerationStatus.GENERATING
    assert current.attempt_count == 2
    assert current.storage_key is None

    # 正しいa2は生成結果を確定できる。
    new_result = repository.record_generated_if_current(
        video_generation_id=second_claim.video_generation_id,
        expected_attempt_number=2,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a2.mp4",
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
        completed_at=_BASE_TIME + timedelta(minutes=22),
    )

    assert new_result is not None
    assert new_result.status is NewsVideoGenerationStatus.GENERATED
    assert new_result.attempt_count == 2
    assert new_result.storage_key == (f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a2.mp4")


def test_record_generated_if_current_does_not_overwrite_completed_video(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert claimed is not None

    original = repository.record_generated_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a1.mp4",
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )

    assert original is not None

    migrated_session.commit()

    # 同じ試行番号であってもGENERATED状態は更新できない。
    duplicate = repository.record_generated_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/other.mp4",
        byte_size=99999,
        content_sha256="f" * 64,
        duration_ms=99999,
        completed_at=_BASE_TIME + timedelta(minutes=7),
    )

    assert duplicate is None

    migrated_session.expire_all()

    loaded = repository.get_by_video_generation_id(claimed.video_generation_id)

    assert loaded == original


def test_record_generated_if_current_rejects_invalid_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    with pytest.raises(
        ValueError,
        match="expected_attempt_number must be at least 1",
    ):
        repository.record_generated_if_current(
            video_generation_id=_VIDEO_GENERATION_1_ID,
            expected_attempt_number=0,
            storage_key="media/video/example/v1/a0.mp4",
            byte_size=12345,
            content_sha256=_CONTENT_HASH,
            duration_ms=10000,
            completed_at=_BASE_TIME + timedelta(minutes=6),
        )


def test_mark_failed_if_current_succeeds(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert claimed is not None
    assert claimed.attempt_count == 1

    completed_at = _BASE_TIME + timedelta(minutes=6)

    failed = repository.mark_failed_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        reason="FFmpeg rendering failed",
        completed_at=completed_at,
    )

    assert failed is not None
    assert failed.status is NewsVideoGenerationStatus.FAILED
    assert failed.attempt_count == 1
    assert failed.failure_reason == "FFmpeg rendering failed"
    assert failed.completed_at == completed_at
    assert failed.storage_key is None
    assert failed.content_sha256 is None

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_video_generation_id(claimed.video_generation_id)

    assert loaded == failed


def test_mark_failed_if_current_rejects_superseded_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert first_claim is not None
    assert first_claim.attempt_count == 1

    # a1 becomes stale. The next attempt, a2, takes ownership.
    second_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=20),
        stale_before=_BASE_TIME + timedelta(minutes=10),
        expected_attempt_number=2,
    )

    assert second_claim is not None
    assert second_claim.attempt_count == 2

    migrated_session.commit()

    # The old a1 job must not mark a2 as failed.
    old_result = repository.mark_failed_if_current(
        video_generation_id=first_claim.video_generation_id,
        expected_attempt_number=1,
        reason="Old FFmpeg process failed",
        completed_at=_BASE_TIME + timedelta(minutes=21),
    )

    assert old_result is None

    migrated_session.expire_all()

    current = repository.get_by_video_generation_id(first_claim.video_generation_id)

    assert current is not None
    assert current.status is NewsVideoGenerationStatus.GENERATING
    assert current.attempt_count == 2
    assert current.failure_reason is None

    # The current a2 job can record its own failure.
    new_result = repository.mark_failed_if_current(
        video_generation_id=second_claim.video_generation_id,
        expected_attempt_number=2,
        reason="Current FFmpeg process failed",
        completed_at=_BASE_TIME + timedelta(minutes=22),
    )

    assert new_result is not None
    assert new_result.status is NewsVideoGenerationStatus.FAILED
    assert new_result.attempt_count == 2
    assert new_result.failure_reason == "Current FFmpeg process failed"


def test_mark_failed_if_current_does_not_overwrite_generated_video(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        video_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
        expected_attempt_number=1,
    )

    assert claimed is not None

    generated = repository.record_generated_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        storage_key=f"media/video/{_MEDIA_PRODUCTION_ID}/v1/a1.mp4",
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )

    assert generated is not None

    migrated_session.commit()

    # A late failure must not overwrite successful generation.
    rejected = repository.mark_failed_if_current(
        video_generation_id=claimed.video_generation_id,
        expected_attempt_number=1,
        reason="Late FFmpeg failure",
        completed_at=_BASE_TIME + timedelta(minutes=7),
    )

    assert rejected is None

    migrated_session.expire_all()

    loaded = repository.get_by_video_generation_id(claimed.video_generation_id)

    assert loaded == generated
    assert loaded is not None
    assert loaded.status is NewsVideoGenerationStatus.GENERATED


def test_mark_failed_if_current_rejects_invalid_attempt(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsVideoGenerationRepository(migrated_session)

    repository.add(_pending_video())

    with pytest.raises(
        ValueError,
        match="expected_attempt_number must be at least 1",
    ):
        repository.mark_failed_if_current(
            video_generation_id=_VIDEO_GENERATION_1_ID,
            expected_attempt_number=0,
            reason="FFmpeg failed",
            completed_at=_BASE_TIME + timedelta(minutes=6),
        )
