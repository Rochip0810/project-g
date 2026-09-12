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
    NewsNarrationAudioStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.models import (
    NewsNarrationAudioGenerationRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsNarrationAudioGenerationRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories.news_narration_audio_generations import (
    NewsNarrationAudioAlreadyExistsError,
    NewsNarrationAudioNotFoundError,
)

_SCRIPT_GENERATION_ID = UUID("93fa2786-2483-4b22-b43f-676658597101")
_MEDIA_PRODUCTION_ID = UUID("93fa2786-2483-4b22-b43f-676658597201")
_AUDIO_GENERATION_1_ID = UUID("93fa2786-2483-4b22-b43f-676658597301")
_AUDIO_GENERATION_2_ID = UUID("93fa2786-2483-4b22-b43f-676658597302")
_INTAKE_ID = UUID("93fa2786-2483-4b22-b43f-676658597401")

_BASE_TIME = datetime(
    2026,
    9,
    12,
    7,
    0,
    tzinfo=UTC,
)

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
    url = "https://www.giants.jp/news/99998/"

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
            text="テスト用の確認済み事実。",
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


def _pending_audio(
    *,
    audio_generation_id: UUID = _AUDIO_GENERATION_1_ID,
    audio_version: int = 1,
) -> NewsNarrationAudioGeneration:
    return NewsNarrationAudioGeneration.pending(
        audio_generation_id=audio_generation_id,
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=audio_version,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_SOURCE_HASH,
        created_at=_BASE_TIME + timedelta(minutes=4),
    )


def _seed_media(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())
    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())
    SqlAlchemyNewsScriptGenerationRepository(session).add(_generated_script())
    SqlAlchemyNewsMediaProductionRepository(session).add(_pending_media())


def test_repository_adds_and_retrieves_narration_audio(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)
    generation = _pending_audio()

    stored = repository.add(generation)

    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == generation
    assert repository.get_by_audio_generation_id(generation.audio_generation_id) == generation
    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            audio_version=1,
        )
        == generation
    )


def test_repository_updates_generated_audio(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    pending = _pending_audio()
    repository.add(pending)

    generated = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=5),
    ).record_generated(
        storage_key=(f"media/audio/{_MEDIA_PRODUCTION_ID}/v1.mp3"),
        byte_size=12345,
        content_sha256=_CONTENT_HASH,
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )

    stored = repository.update(generated)

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_audio_generation_id(generated.audio_generation_id)

    assert stored.status is NewsNarrationAudioStatus.GENERATED
    assert stored.attempt_count == 1
    assert stored.byte_size == 12345
    assert stored.content_sha256 == _CONTENT_HASH
    assert loaded == generated


def test_repository_rejects_duplicate_media_version(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    repository.add(
        _pending_audio(
            audio_generation_id=_AUDIO_GENERATION_1_ID,
            audio_version=1,
        )
    )

    with pytest.raises(NewsNarrationAudioAlreadyExistsError):
        repository.add(
            _pending_audio(
                audio_generation_id=_AUDIO_GENERATION_2_ID,
                audio_version=1,
            )
        )


def test_repository_allows_new_audio_version(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    version_1 = _pending_audio(
        audio_generation_id=_AUDIO_GENERATION_1_ID,
        audio_version=1,
    )
    version_2 = _pending_audio(
        audio_generation_id=_AUDIO_GENERATION_2_ID,
        audio_version=2,
    )

    repository.add(version_1)
    repository.add(version_2)

    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            audio_version=1,
        )
        == version_1
    )
    assert (
        repository.get_by_media_production_version(
            media_production_id=_MEDIA_PRODUCTION_ID,
            audio_version=2,
        )
        == version_2
    )


def test_repository_update_rejects_unknown_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    with pytest.raises(NewsNarrationAudioNotFoundError):
        repository.update(
            _pending_audio(
                audio_generation_id=uuid4(),
            )
        )


def test_database_unique_constraint_blocks_duplicate(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    repository.add(
        _pending_audio(
            audio_generation_id=_AUDIO_GENERATION_1_ID,
            audio_version=1,
        )
    )
    migrated_session.commit()

    duplicate = _pending_audio(
        audio_generation_id=_AUDIO_GENERATION_2_ID,
        audio_version=1,
    )

    migrated_session.add(NewsNarrationAudioGenerationRecord.from_domain(duplicate))

    with pytest.raises(IntegrityError):
        migrated_session.flush()

    migrated_session.rollback()


def test_claim_atomically_starts_pending_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    repository.add(_pending_audio())

    started_at = _BASE_TIME + timedelta(minutes=5)

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=started_at,
    )

    assert claimed is not None
    assert claimed.status is NewsNarrationAudioStatus.GENERATING
    assert claimed.attempt_count == 1
    assert claimed.started_at == started_at
    assert claimed.updated_at == started_at


def test_claim_retries_failed_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    pending = _pending_audio()
    repository.add(pending)

    failed = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=5),
    ).mark_failed(
        reason="temporary TTS failure",
        completed_at=_BASE_TIME + timedelta(minutes=6),
    )
    repository.update(failed)

    retry_at = _BASE_TIME + timedelta(minutes=7)

    claimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=retry_at,
    )

    assert claimed is not None
    assert claimed.status is NewsNarrationAudioStatus.GENERATING
    assert claimed.attempt_count == 2
    assert claimed.failure_reason is None
    assert claimed.completed_at is None


def test_claim_reclaims_stale_generating_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    repository.add(_pending_audio())

    first_started_at = _BASE_TIME + timedelta(minutes=5)

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=first_started_at,
    )

    assert first_claim is not None
    assert first_claim.attempt_count == 1

    reclaimed_at = _BASE_TIME + timedelta(minutes=20)

    reclaimed = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=reclaimed_at,
        stale_before=_BASE_TIME + timedelta(minutes=10),
    )

    assert reclaimed is not None
    assert reclaimed.status is NewsNarrationAudioStatus.GENERATING
    assert reclaimed.attempt_count == 2
    assert reclaimed.started_at == reclaimed_at


def test_claim_does_not_take_fresh_generating_generation(
    migrated_session: Session,
) -> None:
    _seed_media(migrated_session)

    repository = SqlAlchemyNewsNarrationAudioGenerationRepository(migrated_session)

    repository.add(_pending_audio())

    first_started_at = _BASE_TIME + timedelta(minutes=5)

    first_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=first_started_at,
    )

    assert first_claim is not None

    second_claim = repository.claim_by_media_production_version(
        media_production_id=_MEDIA_PRODUCTION_ID,
        audio_version=1,
        started_at=_BASE_TIME + timedelta(minutes=6),
        stale_before=_BASE_TIME + timedelta(minutes=4),
    )

    assert second_claim is None
