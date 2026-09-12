import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from rq import Retry
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

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
    NewsMediaProductionStatus,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsNarrationAudioGenerationRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.storage.local_audio import (
    LocalFileAudioStorage as RealLocalFileAudioStorage,
)
from project_g.interfaces.workers import jobs
from project_g.ports.audio_storage import StoredAudioArtifact
from project_g.ports.speech import SpeechSynthesisRequest

_BASE_TIME = datetime(
    2026,
    9,
    1,
    0,
    0,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("a7a70854-60ef-41d7-8fca-018606510101")
_SCRIPT_ID = UUID("a7a70854-60ef-41d7-8fca-018606510201")
_MEDIA_ID = UUID("a7a70854-60ef-41d7-8fca-018606510301")
_AUDIO_ID = UUID("a7a70854-60ef-41d7-8fca-018606510401")

_FULL_NARRATION = "完成したProject Gナレーション"

_SOURCE_TEXT_SHA256 = hashlib.sha256(_FULL_NARRATION.encode("utf-8")).hexdigest()

_AUDIO_BYTES = b"project-g-test-audio"


class FakeSettings:
    rq_job_timeout_seconds = 180

    openai_api_key = SecretStr("test-key")
    openai_request_timeout_seconds = 12.5

    openai_tts_instructions = "Natural Japanese sports narration."

    def __init__(
        self,
        *,
        media_storage_root: str,
    ) -> None:
        self.media_storage_root = media_storage_root


def _assert_claim_is_committed(
    engine: Engine,
) -> None:
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        generation = SqlAlchemyNewsNarrationAudioGenerationRepository(
            session
        ).get_by_audio_generation_id(_AUDIO_ID)

        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_media_production_id(
            _MEDIA_ID
        )

    assert generation is not None
    assert generation.status is NewsNarrationAudioStatus.GENERATING

    assert media is not None
    assert media.status is NewsMediaProductionStatus.PROCESSING


class RecordingSpeechSynthesizer:
    engine: ClassVar[Engine | None] = None
    calls: ClassVar[list[SpeechSynthesisRequest]] = []

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        assert api_key == "test-key"
        assert timeout_seconds == 12.5

    def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> bytes:
        engine = self.engine

        assert engine is not None

        _assert_claim_is_committed(engine)

        self.calls.append(request)

        return _AUDIO_BYTES


class FailingSpeechSynthesizer:
    engine: ClassVar[Engine | None] = None
    calls: ClassVar[int] = 0

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        assert api_key == "test-key"
        assert timeout_seconds == 12.5

    def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> bytes:
        del request

        engine = self.engine

        assert engine is not None

        _assert_claim_is_committed(engine)

        FailingSpeechSynthesizer.calls += 1

        raise RuntimeError("simulated TTS failure")


class UnexpectedSpeechSynthesizer:
    constructed: ClassVar[int] = 0

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        del api_key
        del timeout_seconds

        UnexpectedSpeechSynthesizer.constructed += 1

    def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> bytes:
        del request

        raise AssertionError("TTS must not be called")


class CheckingAudioStorage:
    engine: ClassVar[Engine | None] = None
    events: ClassVar[list[str]] = []

    def __init__(
        self,
        *,
        root_directory: str | Path,
    ) -> None:
        self._delegate = RealLocalFileAudioStorage(root_directory=root_directory)

    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredAudioArtifact | None:
        engine = self.engine

        assert engine is not None

        _assert_claim_is_committed(engine)

        self.events.append("get")

        return self._delegate.get(storage_key=storage_key)

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredAudioArtifact:
        engine = self.engine

        assert engine is not None

        _assert_claim_is_committed(engine)

        self.events.append("write")

        return self._delegate.write(
            storage_key=storage_key,
            data=data,
        )


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
    url = "https://www.giants.jp/news/99887/"

    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=url,
        canonical_url=url,
        submitted_at=_BASE_TIME,
    )


def _script() -> NewsScriptGeneration:
    evidence = (
        NewsScriptEvidenceSnapshot(
            text="確認済みのテスト事実。",
            source_id="npb_official",
            source_url="https://npb.jp/example/",
            competition_level=(CompetitionLevel.FIRST_TEAM),
            role=EvidenceRole.TARGET,
        ),
    )

    return (
        NewsScriptGeneration.pending(
            generation_id=_SCRIPT_ID,
            intake_id=_INTAKE_ID,
            generation_version=1,
            ranking_score=90,
            created_at=_BASE_TIME,
        )
        .start(
            started_at=(_BASE_TIME + timedelta(minutes=1)),
        )
        .record_generated(
            hook="巨人の最新ニュースです。",
            main_narration=("事実を伝える本文です。"),
            project_g_comment=("ここはしっかり見たいところやな。"),
            closing="今後にも注目です。",
            full_narration=_FULL_NARRATION,
            evidence_snapshot=evidence,
            completed_at=(_BASE_TIME + timedelta(minutes=2)),
        )
    )


def _media() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_MEDIA_ID,
        script_generation_id=_SCRIPT_ID,
        media_version=1,
        created_at=(_BASE_TIME + timedelta(minutes=3)),
    )


def _audio(
    *,
    source_text_sha256: str = (_SOURCE_TEXT_SHA256),
) -> NewsNarrationAudioGeneration:
    return NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=(source_text_sha256),
        created_at=(_BASE_TIME + timedelta(minutes=4)),
    )


def _seed(
    engine: Engine,
    *,
    source_text_sha256: str = (_SOURCE_TEXT_SHA256),
) -> None:
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory.begin() as session:
        SqlAlchemyNewsSourceRepository(session).add(_source())

        SqlAlchemyManualNewsIntakeRepository(session).add(_intake())

        SqlAlchemyNewsScriptGenerationRepository(session).add(_script())

        SqlAlchemyNewsMediaProductionRepository(session).add(_media())

        (
            SqlAlchemyNewsNarrationAudioGenerationRepository(session).add(
                _audio(source_text_sha256=(source_text_sha256))
            )
        )


def _patch_worker(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    storage_root: Path,
    *,
    synthesizer: object,
) -> None:
    settings = FakeSettings(media_storage_root=str(storage_root))

    RecordingSpeechSynthesizer.engine = engine
    FailingSpeechSynthesizer.engine = engine
    CheckingAudioStorage.engine = engine

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: settings,
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _: engine,
    )

    monkeypatch.setattr(
        jobs,
        "OpenAISpeechSynthesizer",
        synthesizer,
    )

    monkeypatch.setattr(
        jobs,
        "LocalFileAudioStorage",
        CheckingAudioStorage,
    )


def _load_states(
    engine: Engine,
) -> tuple[
    NewsNarrationAudioGeneration,
    NewsMediaProduction,
]:
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        generation = SqlAlchemyNewsNarrationAudioGenerationRepository(
            session
        ).get_by_audio_generation_id(_AUDIO_ID)

        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_media_production_id(
            _MEDIA_ID
        )

    assert generation is not None
    assert media is not None

    return generation, media


def test_worker_generates_audio_and_keeps_parent_processing(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    RecordingSpeechSynthesizer.calls = []
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(RecordingSpeechSynthesizer),
    )

    result = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(result, dict)

    assert result["status"] == "generated"

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.GENERATED
    assert generation.attempt_count == 1

    assert generation.storage_key == (f"media/audio/{_MEDIA_ID}/v1.mp3")

    assert generation.byte_size == len(_AUDIO_BYTES)

    assert generation.content_sha256 == (hashlib.sha256(_AUDIO_BYTES).hexdigest())

    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert media.attempt_count == 1
    assert media.completed_at is None

    assert CheckingAudioStorage.events == [
        "get",
        "write",
    ]

    assert len(RecordingSpeechSynthesizer.calls) == 1

    request = RecordingSpeechSynthesizer.calls[0]

    assert request.text == _FULL_NARRATION
    assert request.model == "gpt-4o-mini-tts"
    assert request.voice == "marin"
    assert request.audio_format == "mp3"

    target = tmp_path / "media" / "audio" / str(_MEDIA_ID) / "v1.mp3"

    assert target.read_bytes() == _AUDIO_BYTES

    second = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(second, dict)

    assert second["status"] == "already_generated"

    assert len(RecordingSpeechSynthesizer.calls) == 1


def test_worker_failure_is_durable_and_retryable(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    FailingSpeechSynthesizer.calls = 0
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(FailingSpeechSynthesizer),
    )

    failed = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(failed, dict)

    assert failed["status"] == "failed"

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.FAILED
    assert generation.attempt_count == 1
    assert generation.failure_reason is not None

    assert media.status is NewsMediaProductionStatus.FAILED
    assert media.attempt_count == 1
    assert media.failure_reason is not None

    assert FailingSpeechSynthesizer.calls == 1

    RecordingSpeechSynthesizer.calls = []
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(RecordingSpeechSynthesizer),
    )

    retried = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(retried, dict)

    assert retried["status"] == "generated"

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.GENERATED
    assert generation.attempt_count == 2
    assert generation.failure_reason is None

    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert media.attempt_count == 2
    assert media.failure_reason is None

    assert len(RecordingSpeechSynthesizer.calls) == 1


def test_worker_reuses_existing_artifact_without_tts(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    storage_key = f"media/audio/{_MEDIA_ID}/v1.mp3"

    existing_data = b"recovered-audio"

    RealLocalFileAudioStorage(root_directory=tmp_path).write(
        storage_key=storage_key,
        data=existing_data,
    )

    UnexpectedSpeechSynthesizer.constructed = 0
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(UnexpectedSpeechSynthesizer),
    )

    result = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(result, dict)

    assert result["status"] == "generated"

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.GENERATED

    assert generation.byte_size == len(existing_data)

    assert generation.content_sha256 == (hashlib.sha256(existing_data).hexdigest())

    assert media.status is NewsMediaProductionStatus.PROCESSING

    assert UnexpectedSpeechSynthesizer.constructed == 0

    assert CheckingAudioStorage.events == ["get"]


def test_worker_rejects_source_hash_mismatch_before_tts(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(
        database_engine,
        source_text_sha256="0" * 64,
    )

    UnexpectedSpeechSynthesizer.constructed = 0
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(UnexpectedSpeechSynthesizer),
    )

    with pytest.raises(
        RuntimeError,
        match="source hash",
    ):
        jobs.process_news_narration_audio(str(_AUDIO_ID))

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.PENDING
    assert generation.attempt_count == 0

    assert media.status is NewsMediaProductionStatus.PENDING
    assert media.attempt_count == 0

    assert UnexpectedSpeechSynthesizer.constructed == 0

    assert CheckingAudioStorage.events == []


def _mark_processing(
    engine: Engine,
    *,
    started_at: datetime,
) -> None:
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory.begin() as session:
        audio_repository = SqlAlchemyNewsNarrationAudioGenerationRepository(session)
        media_repository = SqlAlchemyNewsMediaProductionRepository(session)

        claimed = audio_repository.claim_by_media_production_version(
            media_production_id=_MEDIA_ID,
            audio_version=1,
            started_at=started_at,
        )

        assert claimed is not None

        media = media_repository.get_by_media_production_id(_MEDIA_ID)

        assert media is not None

        media_repository.update(media.start(started_at=started_at))


def test_worker_does_not_steal_fresh_generating_attempt(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    started_at = datetime.now(UTC)

    _mark_processing(
        database_engine,
        started_at=started_at,
    )

    UnexpectedSpeechSynthesizer.constructed = 0
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(UnexpectedSpeechSynthesizer),
    )

    result = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(result, Retry)

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.GENERATING
    assert generation.attempt_count == 1
    assert generation.started_at == started_at

    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert media.attempt_count == 1

    assert UnexpectedSpeechSynthesizer.constructed == 0
    assert CheckingAudioStorage.events == []


def test_worker_reclaims_stale_generating_attempt(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    stale_started_at = datetime.now(UTC) - timedelta(minutes=10)

    _mark_processing(
        database_engine,
        started_at=stale_started_at,
    )

    RecordingSpeechSynthesizer.calls = []
    CheckingAudioStorage.events = []

    _patch_worker(
        monkeypatch,
        database_engine,
        tmp_path,
        synthesizer=(RecordingSpeechSynthesizer),
    )

    result = jobs.process_news_narration_audio(str(_AUDIO_ID))

    assert isinstance(result, dict)
    assert result["status"] == "generated"

    generation, media = _load_states(database_engine)

    assert generation.status is NewsNarrationAudioStatus.GENERATED
    assert generation.attempt_count == 2

    # Reclaiming a stale child must not create
    # another parent-media attempt.
    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert media.attempt_count == 1
    assert media.completed_at is None

    assert len(RecordingSpeechSynthesizer.calls) == 1

    assert CheckingAudioStorage.events == [
        "get",
        "write",
    ]
