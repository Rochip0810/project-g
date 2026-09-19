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
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.media_production import NewsMediaProduction
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
from project_g.domain.news.script_generation import NewsScriptGeneration
from project_g.domain.news.video_generation import NewsVideoGeneration
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsNarrationAudioGenerationRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemyNewsVideoGenerationRepository,
)
from project_g.infrastructure.database.repositories.news_video_candidates import (
    SqlAlchemyNewsVideoCandidateRepository,
)
from project_g.ports.repositories.news_video_candidates import (
    NewsVideoCandidate,
)

_BASE_TIME = datetime(2026, 9, 19, 0, 0, tzinfo=UTC)
_AUDIO_HASH = "a" * 64
_VIDEO_HASH = "b" * 64
_TEXT_HASH = "c" * 64


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def _uuid(number: int) -> UUID:
    return UUID(f"11111111-1111-4111-8111-{number:012d}")


def _time(minutes: int) -> datetime:
    return _BASE_TIME + timedelta(minutes=minutes)


def _seed_source(session: Session) -> None:
    SqlAlchemyNewsSourceRepository(session).add(
        NewsSource(
            source_id="giants_official_news",
            name="Giants Official News",
            source_type=SourceType.WEBSITE,
            base_url="https://www.giants.jp/news/",
            is_official=True,
            status=SourceStatus.PAUSED,
            priority=100,
        )
    )


def _seed_media(
    session: Session,
    number: int,
    *,
    status: str = "processing",
) -> None:
    url = f"https://www.giants.jp/news/{90000 + number}/"

    intake = ManualNewsIntake(
        intake_id=_uuid(100 + number),
        source_id="giants_official_news",
        submitted_url=url,
        canonical_url=url,
        submitted_at=_time(0),
    )

    SqlAlchemyManualNewsIntakeRepository(session).add(intake)

    script = (
        NewsScriptGeneration.pending(
            generation_id=_uuid(200 + number),
            intake_id=intake.intake_id,
            generation_version=1,
            ranking_score=90,
            created_at=_time(0),
        )
        .start(started_at=_time(1))
        .record_generated(
            hook="巨人の最新情報です。",
            main_narration="ニュース本文です。",
            project_g_comment="ここは注目やな。",
            closing=None,
            full_narration="完成したナレーション全文",
            evidence_snapshot=(),
            completed_at=_time(2),
        )
    )

    SqlAlchemyNewsScriptGenerationRepository(session).add(script)

    media = NewsMediaProduction.pending(
        media_production_id=_uuid(300 + number),
        script_generation_id=script.generation_id,
        media_version=1,
        created_at=_time(3) + timedelta(seconds=number),
    )

    if status != "pending":
        media = media.start(started_at=_time(4))

        if status == "failed":
            media = media.mark_failed(
                reason="Video generation failed",
                completed_at=_time(7),
            )
        elif status == "ready":
            media = media.mark_ready(completed_at=_time(7))

    SqlAlchemyNewsMediaProductionRepository(session).add(media)


def _seed_audio(
    session: Session,
    number: int,
    *,
    status: str = "generated",
    audio_version: int = 1,
) -> NewsNarrationAudioGeneration:
    audio = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_uuid(400 + number),
        media_production_id=_uuid(300 + number),
        audio_version=audio_version,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_TEXT_HASH,
        created_at=_time(4),
    )

    if status != "pending":
        audio = audio.start(started_at=_time(5))

        if status == "generated":
            audio = audio.record_generated(
                storage_key=f"media/audio/{_uuid(300 + number)}/v{audio_version}.mp3",
                byte_size=12345,
                content_sha256=_AUDIO_HASH,
                completed_at=_time(6),
            )
        elif status == "failed":
            audio = audio.mark_failed(
                reason="TTS failed",
                completed_at=_time(6),
            )

    SqlAlchemyNewsNarrationAudioGenerationRepository(session).add(audio)

    return audio


def _seed_video(
    session: Session,
    number: int,
    *,
    status: str,
    video_version: int = 1,
) -> None:
    video = NewsVideoGeneration.pending(
        video_generation_id=_uuid(500 + number),
        media_production_id=_uuid(300 + number),
        video_version=video_version,
        renderer="ffmpeg",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
        source_audio_generation_id=_uuid(400 + number),
        source_audio_sha256=_AUDIO_HASH,
        created_at=_time(8),
    )

    if status != "pending":
        started_at = _time(11) if status == "fresh" else _time(9)

        video = video.start(started_at=started_at)

        if status == "failed":
            video = video.mark_failed(
                reason="FFmpeg failed",
                completed_at=_time(10),
            )
        elif status == "generated":
            video = video.record_generated(
                storage_key=f"media/video/{_uuid(300 + number)}/v{video_version}.mp4",
                byte_size=23456,
                content_sha256=_VIDEO_HASH,
                duration_ms=12345,
                completed_at=_time(10),
            )

    SqlAlchemyNewsVideoGenerationRepository(session).add(video)


def _candidates(
    session: Session,
    *,
    audio_version: int = 1,
    video_version: int = 1,
    limit: int = 50,
    stale_before: datetime | None = None,
) -> tuple[NewsVideoCandidate, ...]:
    repository = SqlAlchemyNewsVideoCandidateRepository(session)

    return repository.list_candidates(
        audio_version=audio_version,
        video_version=video_version,
        stale_before=stale_before or _time(10),
        limit=limit,
    )


def test_generated_audio_is_selected_with_exact_source_metadata(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    _seed_media(migrated_session, 1)
    _seed_audio(migrated_session, 1)

    candidates = _candidates(migrated_session)

    assert len(candidates) == 1

    candidate = candidates[0]

    assert candidate.media_production.media_production_id == _uuid(301)
    assert candidate.source_audio.audio_generation_id == _uuid(401)
    assert candidate.source_audio.audio_version == 1
    assert candidate.source_audio.content_sha256 == _AUDIO_HASH
    assert candidate.source_audio.storage_key == (f"media/audio/{_uuid(301)}/v1.mp3")


def test_missing_or_unfinished_audio_is_not_selected(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)

    _seed_media(migrated_session, 1)

    _seed_media(migrated_session, 2)
    _seed_audio(migrated_session, 2, status="pending")

    _seed_media(migrated_session, 3)
    _seed_audio(migrated_session, 3, status="failed")

    _seed_media(migrated_session, 4)
    _seed_audio(migrated_session, 4, status="generated")

    candidates = _candidates(migrated_session)

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(304)


def test_video_status_controls_candidate_eligibility(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)

    statuses = {
        1: None,
        2: "generated",
        3: "pending",
        4: "failed",
        5: "stale",
        6: "fresh",
    }

    for number, video_status in statuses.items():
        _seed_media(migrated_session, number)
        _seed_audio(migrated_session, number)

        if video_status is not None:
            _seed_video(
                migrated_session,
                number,
                status=video_status,
            )

    candidates = _candidates(migrated_session)

    selected_ids = {candidate.media_production.media_production_id for candidate in candidates}

    assert selected_ids == {
        _uuid(301),
        _uuid(303),
        _uuid(304),
        _uuid(305),
    }


def test_parent_status_controls_candidate_eligibility(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)

    statuses = {
        1: "pending",
        2: "processing",
        3: "failed",
        4: "ready",
    }

    for number, status in statuses.items():
        _seed_media(
            migrated_session,
            number,
            status=status,
        )
        _seed_audio(migrated_session, number)

    candidates = _candidates(migrated_session)

    selected_ids = {candidate.media_production.media_production_id for candidate in candidates}

    assert selected_ids == {
        _uuid(302),
        _uuid(303),
    }


def test_candidate_selects_requested_audio_and_video_versions(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)

    _seed_media(migrated_session, 1)
    _seed_audio(migrated_session, 1, audio_version=2)

    _seed_media(migrated_session, 2)
    _seed_audio(migrated_session, 2, audio_version=1)

    candidates = _candidates(
        migrated_session,
        audio_version=2,
        video_version=3,
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)
    assert candidates[0].source_audio.audio_version == 2


def test_candidate_uses_requested_video_version(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    _seed_media(migrated_session, 1)
    _seed_audio(migrated_session, 1)

    _seed_video(
        migrated_session,
        1,
        status="generated",
        video_version=1,
    )

    # Video v1 is complete, but Video v2 has not been created.
    candidates = _candidates(
        migrated_session,
        video_version=2,
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)

    # The already-generated Video v1 must not be selected again.
    assert (
        _candidates(
            migrated_session,
            video_version=1,
        )
        == ()
    )


def test_candidate_limit_preserves_creation_order(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)

    for number in (3, 1, 2):
        _seed_media(migrated_session, number)
        _seed_audio(migrated_session, number)

    candidates = _candidates(
        migrated_session,
        limit=2,
    )

    assert [candidate.media_production.media_production_id for candidate in candidates] == [
        _uuid(301),
        _uuid(302),
    ]


@pytest.mark.parametrize(
    ("audio_version", "video_version", "limit"),
    [
        (0, 1, 5),
        (1, 0, 5),
        (1, 1, 0),
        (1, 1, 51),
    ],
)
def test_candidate_rejects_invalid_parameters(
    migrated_session: Session,
    audio_version: int,
    video_version: int,
    limit: int,
) -> None:
    repository = SqlAlchemyNewsVideoCandidateRepository(migrated_session)

    with pytest.raises(ValueError):
        repository.list_candidates(
            audio_version=audio_version,
            video_version=video_version,
            stale_before=_time(10),
            limit=limit,
        )


def test_candidate_rejects_naive_stale_before(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsVideoCandidateRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="stale_before must be timezone-aware",
    ):
        repository.list_candidates(
            audio_version=1,
            video_version=1,
            stale_before=datetime(2026, 9, 19, 0, 10),
            limit=5,
        )


def test_stale_generating_is_selected_at_boundary(
    migrated_session: Session,
) -> None:
    _seed_source(migrated_session)
    _seed_media(migrated_session, 1)
    _seed_audio(migrated_session, 1)
    _seed_video(
        migrated_session,
        1,
        status="stale",
    )

    # Video started exactly at stale_before.
    candidates = _candidates(
        migrated_session,
        stale_before=_time(9),
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)

    # One second earlier, the same video is not yet stale.
    candidates = _candidates(
        migrated_session,
        stale_before=_time(9) - timedelta(seconds=1),
    )

    assert candidates == ()
