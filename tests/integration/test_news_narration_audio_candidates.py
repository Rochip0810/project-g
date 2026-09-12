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
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsNarrationAudioCandidateRepository,
    SqlAlchemyNewsNarrationAudioGenerationRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)

_BASE_TIME = datetime(
    2026,
    9,
    12,
    9,
    0,
    tzinfo=UTC,
)

_SOURCE_ID = "giants_official_news"
_SOURCE_HASH = "a" * 64
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


def _uuid(number: int) -> UUID:
    return UUID(f"11111111-1111-4111-8111-{number:012d}")


def _source() -> NewsSource:
    return NewsSource(
        source_id=_SOURCE_ID,
        name="Giants Official News",
        source_type=SourceType.WEBSITE,
        base_url="https://www.giants.jp/news/",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=100,
    )


def _intake(
    number: int,
) -> ManualNewsIntake:
    url = f"https://www.giants.jp/news/{90000 + number}/"

    return ManualNewsIntake(
        intake_id=_uuid(100 + number),
        source_id=_SOURCE_ID,
        submitted_url=url,
        canonical_url=url,
        submitted_at=_BASE_TIME + timedelta(seconds=number),
    )


def _script(
    number: int,
) -> NewsScriptGeneration:
    evidence = (
        NewsScriptEvidenceSnapshot(
            text="確認済みのテスト事実。",
            source_id="npb_official",
            source_url="https://npb.jp/example/",
            competition_level=CompetitionLevel.FIRST_TEAM,
            role=EvidenceRole.TARGET,
        ),
    )

    created_at = _BASE_TIME + timedelta(minutes=number)

    return (
        NewsScriptGeneration.pending(
            generation_id=_uuid(200 + number),
            intake_id=_uuid(100 + number),
            generation_version=1,
            ranking_score=90,
            created_at=created_at,
        )
        .start(
            started_at=created_at + timedelta(seconds=10),
        )
        .record_generated(
            hook="巨人の最新情報です。",
            main_narration="事実を伝える本文です。",
            project_g_comment="ここはしっかり見たいところやな。",
            closing="今後にも注目です。",
            full_narration=f"完成ナレーション {number}",
            evidence_snapshot=evidence,
            completed_at=created_at + timedelta(seconds=20),
        )
    )


def _media(
    number: int,
) -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_uuid(300 + number),
        script_generation_id=_uuid(200 + number),
        media_version=1,
        created_at=_BASE_TIME + timedelta(minutes=number, seconds=30),
    )


def _seed_base(
    session: Session,
    *,
    numbers: tuple[int, ...],
) -> None:
    source_repository = SqlAlchemyNewsSourceRepository(session)
    intake_repository = SqlAlchemyManualNewsIntakeRepository(session)
    script_repository = SqlAlchemyNewsScriptGenerationRepository(session)
    media_repository = SqlAlchemyNewsMediaProductionRepository(session)

    source_repository.add(_source())

    for number in numbers:
        intake_repository.add(_intake(number))
        script_repository.add(_script(number))
        media_repository.add(_media(number))


def _pending_audio(
    number: int,
) -> NewsNarrationAudioGeneration:
    return NewsNarrationAudioGeneration.pending(
        audio_generation_id=_uuid(400 + number),
        media_production_id=_uuid(300 + number),
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_SOURCE_HASH,
        created_at=_BASE_TIME + timedelta(minutes=number, seconds=40),
    )


def test_candidate_repository_returns_pending_without_audio(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(1,),
    )

    repository = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session)

    candidates = repository.list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(hours=1),
        limit=5,
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)
    assert candidates[0].full_narration == ("完成ナレーション 1")


def test_generated_audio_is_skipped(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(1,),
    )

    audio_repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    pending = _pending_audio(1)
    audio_repository.add(pending)

    generated = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=10),
    ).record_generated(
        storage_key="media/audio/example/v1.mp3",
        byte_size=100,
        content_sha256=_CONTENT_HASH,
        completed_at=_BASE_TIME + timedelta(minutes=11),
    )
    audio_repository.update(generated)

    candidates = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session).list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(hours=1),
        limit=5,
    )

    assert candidates == ()


def test_failed_audio_is_retry_candidate(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(1,),
    )

    media_repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)
    audio_repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    media = media_repository.get_by_media_production_id(_uuid(301))
    assert media is not None

    processing = media.start(
        started_at=_BASE_TIME + timedelta(minutes=8),
    )
    failed_media = processing.mark_failed(
        reason="TTS failed",
        completed_at=_BASE_TIME + timedelta(minutes=9),
    )
    media_repository.update(failed_media)

    pending = _pending_audio(1)
    audio_repository.add(pending)

    failed_audio = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=8),
    ).mark_failed(
        reason="TTS failed",
        completed_at=_BASE_TIME + timedelta(minutes=9),
    )
    audio_repository.update(failed_audio)

    candidates = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session).list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(hours=1),
        limit=5,
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)


def test_fresh_generating_audio_is_skipped(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(1,),
    )

    media_repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)
    audio_repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    media = media_repository.get_by_media_production_id(_uuid(301))
    assert media is not None

    media_repository.update(
        media.start(
            started_at=_BASE_TIME + timedelta(minutes=10),
        )
    )

    pending = _pending_audio(1)
    audio_repository.add(pending)

    claimed = audio_repository.claim_by_media_production_version(
        media_production_id=_uuid(301),
        audio_version=1,
        started_at=_BASE_TIME + timedelta(minutes=10),
    )
    assert claimed is not None

    candidates = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session).list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(minutes=9),
        limit=5,
    )

    assert candidates == ()


def test_stale_generating_audio_is_candidate(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(1,),
    )

    media_repository = SqlAlchemyNewsMediaProductionRepository(migrated_session)
    audio_repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    media = media_repository.get_by_media_production_id(_uuid(301))
    assert media is not None

    media_repository.update(
        media.start(
            started_at=_BASE_TIME + timedelta(minutes=5),
        )
    )

    audio_repository.add(_pending_audio(1))

    claimed = audio_repository.claim_by_media_production_version(
        media_production_id=_uuid(301),
        audio_version=1,
        started_at=_BASE_TIME + timedelta(minutes=5),
    )
    assert claimed is not None

    candidates = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session).list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(minutes=6),
        limit=5,
    )

    assert len(candidates) == 1
    assert candidates[0].media_production.media_production_id == _uuid(301)


def test_candidates_are_deterministic_and_limited(
    migrated_session: Session,
) -> None:
    _seed_base(
        migrated_session,
        numbers=(3, 1, 2),
    )

    candidates = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session).list_candidates(
        audio_version=1,
        stale_before=_BASE_TIME + timedelta(hours=1),
        limit=2,
    )

    assert [candidate.media_production.media_production_id for candidate in candidates] == [
        _uuid(301),
        _uuid(302),
    ]


@pytest.mark.parametrize(
    ("audio_version", "limit"),
    (
        (0, 5),
        (1, 0),
        (1, 51),
    ),
)
def test_candidate_repository_rejects_invalid_options(
    migrated_session: Session,
    audio_version: int,
    limit: int,
) -> None:
    repository = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session)

    with pytest.raises(ValueError):
        repository.list_candidates(
            audio_version=audio_version,
            stale_before=_BASE_TIME,
            limit=limit,
        )


def test_candidate_repository_rejects_naive_stale_before(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsNarrationAudioCandidateRepository(migrated_session)

    with pytest.raises(
        ValueError,
        match="stale_before must be timezone-aware",
    ):
        repository.list_candidates(
            audio_version=1,
            stale_before=datetime(2026, 9, 12, 9, 0),
            limit=5,
        )
