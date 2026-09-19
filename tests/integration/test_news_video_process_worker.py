import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
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
from project_g.domain.news.media_production import (
    NewsMediaProduction,
    NewsMediaProductionStatus,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsMediaProductionRepository,
    SqlAlchemyNewsNarrationAudioGenerationRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemyNewsVideoGenerationRepository,
)
from project_g.infrastructure.storage.local_audio import (
    LocalFileAudioStorage,
)
from project_g.interfaces.workers import jobs
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)
from project_g.ports.video import (
    RenderedVideo,
    VideoRenderRequest,
)

_BASE_TIME = datetime(
    2026,
    9,
    18,
    7,
    0,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00401")
_SCRIPT_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00101")
_MEDIA_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00201")
_AUDIO_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00202")
_VIDEO_ID = UUID("5af3ad8c-77ef-40c8-8a28-a95f5ba00301")

_AUDIO_BYTES = b"project-g-video-worker-test-audio"
_VIDEO_BYTES = b"project-g-video-worker-test-video"

_AUDIO_HASH = hashlib.sha256(_AUDIO_BYTES).hexdigest()
_VIDEO_HASH = hashlib.sha256(_VIDEO_BYTES).hexdigest()

_AUDIO_KEY = f"media/audio/{_MEDIA_ID}/v1.mp3"
_VIDEO_KEY = f"media/video/{_MEDIA_ID}/v1/a1.mp4"


def _time(minutes: int) -> datetime:
    return _BASE_TIME + timedelta(minutes=minutes)


def _seed(database_engine: Engine) -> None:
    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory.begin() as session:
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

        url = "https://www.giants.jp/news/99997/"

        SqlAlchemyManualNewsIntakeRepository(session).add(
            ManualNewsIntake(
                intake_id=_INTAKE_ID,
                source_id="giants_official_news",
                submitted_url=url,
                canonical_url=url,
                submitted_at=_time(0),
            )
        )

        script = (
            NewsScriptGeneration.pending(
                generation_id=_SCRIPT_ID,
                intake_id=_INTAKE_ID,
                generation_version=1,
                ranking_score=90,
                created_at=_time(0),
            )
            .start(
                started_at=_time(1),
            )
            .record_generated(
                hook="巨人の最新ニュースです。",
                main_narration="ニュース本文です。",
                project_g_comment="ここは注目やな。",
                closing="今後の動きにも注目です。",
                full_narration="完成したナレーション全文",
                evidence_snapshot=(),
                completed_at=_time(2),
            )
        )

        SqlAlchemyNewsScriptGenerationRepository(session).add(script)

        media = NewsMediaProduction.pending(
            media_production_id=_MEDIA_ID,
            script_generation_id=_SCRIPT_ID,
            media_version=1,
            created_at=_time(3),
        ).start(
            started_at=_time(4),
        )

        SqlAlchemyNewsMediaProductionRepository(session).add(media)

        audio = (
            NewsNarrationAudioGeneration.pending(
                audio_generation_id=_AUDIO_ID,
                media_production_id=_MEDIA_ID,
                audio_version=1,
                provider="openai",
                model="gpt-4o-mini-tts",
                voice="marin",
                audio_format="mp3",
                source_text_sha256="c" * 64,
                created_at=_time(5),
            )
            .start(
                started_at=_time(6),
            )
            .record_generated(
                storage_key=_AUDIO_KEY,
                byte_size=len(_AUDIO_BYTES),
                content_sha256=_AUDIO_HASH,
                completed_at=_time(7),
            )
        )

        SqlAlchemyNewsNarrationAudioGenerationRepository(session).add(audio)

        video = NewsVideoGeneration.pending(
            video_generation_id=_VIDEO_ID,
            media_production_id=_MEDIA_ID,
            video_version=1,
            renderer="ffmpeg",
            video_format="mp4",
            width=1080,
            height=1920,
            fps=30,
            source_audio_generation_id=_AUDIO_ID,
            source_audio_sha256=_AUDIO_HASH,
            created_at=_time(8),
        )

        SqlAlchemyNewsVideoGenerationRepository(session).add(video)


def _load_states(
    database_engine: Engine,
) -> tuple[
    NewsVideoGeneration,
    NewsMediaProduction,
    NewsNarrationAudioGeneration,
]:
    with Session(database_engine) as session:
        video = SqlAlchemyNewsVideoGenerationRepository(session).get_by_video_generation_id(
            _VIDEO_ID
        )

        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_media_production_id(
            _MEDIA_ID
        )

        audio = SqlAlchemyNewsNarrationAudioGenerationRepository(
            session
        ).get_by_audio_generation_id(_AUDIO_ID)

        assert video is not None
        assert media is not None
        assert audio is not None

        return video, media, audio


class CheckingVideoRenderer:
    def __init__(
        self,
        database_engine: Engine,
    ) -> None:
        self.database_engine = database_engine
        self.requests: list[VideoRenderRequest] = []

    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        self.requests.append(request)

        # This uses a separate DB session to verify that
        # the worker committed its claim before rendering.
        video, media, audio = _load_states(self.database_engine)

        assert video.status is NewsVideoGenerationStatus.GENERATING
        assert video.attempt_count == 1

        assert media.status is NewsMediaProductionStatus.PROCESSING
        assert audio.status is NewsNarrationAudioStatus.GENERATED

        return RenderedVideo(
            data=_VIDEO_BYTES,
            duration_ms=12000,
        )


def test_video_worker_generates_mp4_and_marks_media_ready(
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

    # Store the real input bytes using the production
    # audio-storage implementation.
    LocalFileAudioStorage(
        root_directory=tmp_path,
    ).write(
        storage_key=_AUDIO_KEY,
        data=_AUDIO_BYTES,
    )

    renderer = CheckingVideoRenderer(database_engine)

    # Replace only external configuration and FFmpeg.
    # The DB repositories and file storage remain real.
    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: SimpleNamespace(
            media_storage_root=str(tmp_path),
            rq_job_timeout_seconds=300,
        ),
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: database_engine,
    )

    monkeypatch.setattr(
        jobs,
        "FFmpegVideoRenderer",
        lambda: renderer,
    )

    result = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    assert result["status"] == "generated"
    assert result["video_generation_id"] == str(_VIDEO_ID)
    assert result["media_production_id"] == str(_MEDIA_ID)
    assert result["storage_key"] == _VIDEO_KEY
    assert result["byte_size"] == len(_VIDEO_BYTES)
    assert result["content_sha256"] == _VIDEO_HASH
    assert result["duration_ms"] == 12000
    assert result["expected_attempt_number"] == 1

    # FFmpeg must receive the verified source audio.
    assert renderer.requests == [
        VideoRenderRequest(
            audio_data=_AUDIO_BYTES,
            audio_format="mp3",
            video_format="mp4",
            width=1080,
            height=1920,
            fps=30,
        )
    ]

    # Verify the actual file stored on disk.
    video_path = tmp_path / _VIDEO_KEY

    assert video_path.is_file()
    assert video_path.read_bytes() == _VIDEO_BYTES

    # Verify the committed database state.
    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.GENERATED
    assert video.attempt_count == 1
    assert video.storage_key == _VIDEO_KEY
    assert video.byte_size == len(_VIDEO_BYTES)
    assert video.content_sha256 == _VIDEO_HASH
    assert video.duration_ms == 12000

    assert media.status is NewsMediaProductionStatus.READY
    assert media.attempt_count == 1
    assert media.completed_at is not None

    assert audio.status is NewsNarrationAudioStatus.GENERATED

    # Re-running a completed generation must not
    # render or save another video.
    second_result = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    assert second_result["status"] == "already_generated"
    assert len(renderer.requests) == 1


@pytest.mark.parametrize(
    "audio_bytes",
    [
        pytest.param(None, id="missing-audio"),
        pytest.param(
            b"corrupted-audio-data",
            id="corrupted-audio",
        ),
    ],
)
def test_video_worker_invalid_audio_marks_generation_failed(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    audio_bytes: bytes | None,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    # None represents a missing audio file.
    # Other bytes represent a file whose SHA-256
    # does not match the persisted audio metadata.
    if audio_bytes is not None:
        LocalFileAudioStorage(
            root_directory=tmp_path,
        ).write(
            storage_key=_AUDIO_KEY,
            data=audio_bytes,
        )

    renderer = CheckingVideoRenderer(database_engine)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: SimpleNamespace(
            media_storage_root=str(tmp_path),
            rq_job_timeout_seconds=300,
        ),
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: database_engine,
    )

    monkeypatch.setattr(
        jobs,
        "FFmpegVideoRenderer",
        lambda: renderer,
    )

    result = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    # The worker records the failure as durable state.
    assert result["status"] == "failed"
    assert result["video_generation_id"] == str(_VIDEO_ID)
    assert result["expected_attempt_number"] == 1
    assert result["failure_type"] == "RuntimeError"

    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.FAILED
    assert video.attempt_count == 1
    assert video.failure_reason is not None
    assert video.completed_at is not None
    assert video.storage_key is None
    assert video.content_sha256 is None

    assert media.status is NewsMediaProductionStatus.FAILED
    assert media.attempt_count == 1
    assert media.failure_reason is not None
    assert media.completed_at is not None

    # The source audio record itself must remain unchanged.
    assert audio.status is NewsNarrationAudioStatus.GENERATED
    assert audio.content_sha256 == _AUDIO_HASH

    # Invalid source audio must never reach FFmpeg.
    assert renderer.requests == []

    # No video artifact should have been written.
    assert not (tmp_path / _VIDEO_KEY).exists()


class FailingThenSuccessfulVideoRenderer:
    def __init__(
        self,
        database_engine: Engine,
    ) -> None:
        self.database_engine = database_engine
        self.requests: list[VideoRenderRequest] = []
        self.observed_attempts: list[int] = []

    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        self.requests.append(request)

        # Verify that the claim has committed before
        # the external rendering operation begins.
        video, media, audio = _load_states(self.database_engine)

        assert video.status is NewsVideoGenerationStatus.GENERATING
        assert media.status is NewsMediaProductionStatus.PROCESSING
        assert audio.status is NewsNarrationAudioStatus.GENERATED

        self.observed_attempts.append(video.attempt_count)

        if len(self.requests) == 1:
            raise RuntimeError("Simulated FFmpeg rendering failure")

        return RenderedVideo(
            data=_VIDEO_BYTES,
            duration_ms=12000,
        )


def test_video_worker_recovers_from_ffmpeg_failure(
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

    # Store the real source audio artifact.
    LocalFileAudioStorage(
        root_directory=tmp_path,
    ).write(
        storage_key=_AUDIO_KEY,
        data=_AUDIO_BYTES,
    )

    renderer = FailingThenSuccessfulVideoRenderer(database_engine)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: SimpleNamespace(
            media_storage_root=str(tmp_path),
            rq_job_timeout_seconds=300,
        ),
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: database_engine,
    )

    monkeypatch.setattr(
        jobs,
        "FFmpegVideoRenderer",
        lambda: renderer,
    )

    # -------------------------------------------------
    # Attempt 1: FFmpeg fails.
    # -------------------------------------------------

    first = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    assert first["status"] == "failed"
    assert first["expected_attempt_number"] == 1
    assert first["failure_type"] == "RuntimeError"

    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.FAILED
    assert video.attempt_count == 1
    assert video.failure_reason is not None
    assert video.storage_key is None

    assert media.status is NewsMediaProductionStatus.FAILED
    assert media.attempt_count == 1
    assert media.failure_reason is not None

    assert audio.status is NewsNarrationAudioStatus.GENERATED

    # No video is persisted after rendering failure.
    assert not (tmp_path / _VIDEO_KEY).exists()

    assert renderer.observed_attempts == [1]
    assert len(renderer.requests) == 1

    # -------------------------------------------------
    # The old a1 job cannot claim a new attempt.
    # -------------------------------------------------

    old_job = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    assert old_job["status"] == "not_claimed"

    video, media, _ = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.FAILED
    assert video.attempt_count == 1

    assert media.status is NewsMediaProductionStatus.FAILED

    # An obsolete job must not trigger FFmpeg.
    assert len(renderer.requests) == 1

    # -------------------------------------------------
    # Attempt 2: FFmpeg succeeds.
    # -------------------------------------------------

    second = jobs.process_news_video(
        str(_VIDEO_ID),
        2,
    )

    expected_video_key = f"media/video/{_MEDIA_ID}/v1/a2.mp4"

    assert second["status"] == "generated"
    assert second["expected_attempt_number"] == 2
    assert second["video_generation_id"] == str(_VIDEO_ID)
    assert second["storage_key"] == expected_video_key
    assert second["content_sha256"] == _VIDEO_HASH
    assert second["duration_ms"] == 12000

    # FFmpeg must run exactly once for each valid attempt.
    assert renderer.observed_attempts == [1, 2]
    assert len(renderer.requests) == 2

    for request in renderer.requests:
        assert request.audio_data == _AUDIO_BYTES

    # The successful artifact belongs to attempt a2.
    video_path = tmp_path / expected_video_key

    assert video_path.is_file()
    assert video_path.read_bytes() == _VIDEO_BYTES

    # The failed attempt must not have produced an artifact.
    assert not (tmp_path / _VIDEO_KEY).exists()

    # -------------------------------------------------
    # Verify the final committed DB state.
    # -------------------------------------------------

    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.GENERATED
    assert video.attempt_count == 2
    assert video.failure_reason is None
    assert video.storage_key == expected_video_key
    assert video.byte_size == len(_VIDEO_BYTES)
    assert video.content_sha256 == _VIDEO_HASH
    assert video.duration_ms == 12000
    assert video.completed_at is not None

    assert media.status is NewsMediaProductionStatus.READY
    assert media.attempt_count == 2
    assert media.failure_reason is None
    assert media.completed_at is not None

    assert audio.status is NewsNarrationAudioStatus.GENERATED
    assert audio.content_sha256 == _AUDIO_HASH


class SupersedingVideoRenderer:
    """Simulate another worker reclaiming a1 during rendering."""

    def __init__(
        self,
        database_engine: Engine,
    ) -> None:
        self.database_engine = database_engine
        self.requests: list[VideoRenderRequest] = []
        self.reclaimed_attempt: int | None = None

    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        self.requests.append(request)

        # The original worker must have committed its claim.
        video, media, audio = _load_states(self.database_engine)

        assert video.status is NewsVideoGenerationStatus.GENERATING
        assert video.attempt_count == 1
        assert video.started_at is not None

        assert media.status is NewsMediaProductionStatus.PROCESSING
        assert audio.status is NewsNarrationAudioStatus.GENERATED

        # Simulate the original attempt becoming stale.
        # Use a separate transaction to reclaim it as a2.
        reclaimed_at = video.started_at + timedelta(seconds=1)

        factory = sessionmaker(
            bind=self.database_engine,
            expire_on_commit=False,
        )

        with factory.begin() as session:
            repository = SqlAlchemyNewsVideoGenerationRepository(session)

            reclaimed = repository.claim_by_media_production_version(
                media_production_id=_MEDIA_ID,
                video_version=1,
                started_at=reclaimed_at,
                stale_before=reclaimed_at,
                expected_attempt_number=2,
            )

            assert reclaimed is not None
            assert reclaimed.video_generation_id == _VIDEO_ID
            assert reclaimed.status is NewsVideoGenerationStatus.GENERATING
            assert reclaimed.attempt_count == 2

            self.reclaimed_attempt = reclaimed.attempt_count

        # The a2 claim has committed. The old a1 renderer
        # now finishes and returns its video bytes.
        return RenderedVideo(
            data=_VIDEO_BYTES,
            duration_ms=12000,
        )


def test_video_worker_cannot_complete_superseded_attempt(
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

    LocalFileAudioStorage(
        root_directory=tmp_path,
    ).write(
        storage_key=_AUDIO_KEY,
        data=_AUDIO_BYTES,
    )

    renderer = SupersedingVideoRenderer(database_engine)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: SimpleNamespace(
            media_storage_root=str(tmp_path),
            rq_job_timeout_seconds=300,
        ),
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: database_engine,
    )

    monkeypatch.setattr(
        jobs,
        "FFmpegVideoRenderer",
        lambda: renderer,
    )

    # a1 starts rendering. During rendering, the fake
    # renderer commits a new claim for attempt a2.
    result = jobs.process_news_video(
        str(_VIDEO_ID),
        1,
    )

    # The original worker must not commit its result.
    assert result["status"] == "superseded"
    assert result["video_generation_id"] == str(_VIDEO_ID)
    assert result["expected_attempt_number"] == 1

    assert renderer.reclaimed_attempt == 2
    assert len(renderer.requests) == 1

    # The original attempt may have written its own file.
    # Its artifact must remain isolated under the a1 key.
    original_artifact = tmp_path / _VIDEO_KEY

    assert original_artifact.is_file()
    assert original_artifact.read_bytes() == _VIDEO_BYTES

    # The new attempt's file must not be overwritten
    # or created by the original worker.
    second_artifact = tmp_path / f"media/video/{_MEDIA_ID}/v1/a2.mp4"

    assert not second_artifact.exists()

    # Verify the committed database state.
    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.GENERATING
    assert video.attempt_count == 2
    assert video.storage_key is None
    assert video.content_sha256 is None
    assert video.completed_at is None

    # The old worker must not mark the parent READY.
    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert media.completed_at is None

    # The source audio is unaffected.
    assert audio.status is NewsNarrationAudioStatus.GENERATED
    assert audio.content_sha256 == _AUDIO_HASH


def test_video_prepare_worker_persists_and_enqueues(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Mapping, Sequence

    command.upgrade(
        alembic_config,
        "head",
    )

    _seed(database_engine)

    class FakePool:
        def close(self) -> None:
            pass

    class FakeConnection:
        def close(self) -> None:
            pass

    class FakeRedis:
        @staticmethod
        def from_pool(_pool: object) -> FakeConnection:
            return FakeConnection()

    class RecordingQueueProvider:
        calls: ClassVar[list[dict[str, object]]] = []

        def __init__(
            self,
            _settings: object,
            _connection: object,
        ) -> None:
            pass

        def enqueue(
            self,
            queue_name: QueueName,
            function_path: str,
            *,
            args: Sequence[JobArgument] = (),
            kwargs: Mapping[str, JobArgument] | None = None,
            job_id: str | None = None,
            description: str | None = None,
        ) -> JobSnapshot:
            assert job_id is not None

            # The video record must already be durable
            # when the worker enqueues the processing job.
            video, media, audio = _load_states(database_engine)

            assert video.status is NewsVideoGenerationStatus.PENDING
            assert video.attempt_count == 0

            assert media.status is NewsMediaProductionStatus.PROCESSING
            assert audio.status is NewsNarrationAudioStatus.GENERATED

            self.calls.append(
                {
                    "queue_name": queue_name,
                    "function_path": function_path,
                    "args": tuple(args),
                    "kwargs": kwargs,
                    "job_id": job_id,
                    "description": description,
                }
            )

            return JobSnapshot(
                job_id=job_id,
                queue=queue_name,
                status="queued",
            )

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: SimpleNamespace(
            rq_job_timeout_seconds=300,
        ),
    )

    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: database_engine,
    )

    monkeypatch.setattr(
        jobs,
        "create_redis_connection_pool",
        lambda *_args, **_kwargs: FakePool(),
    )

    monkeypatch.setattr(
        jobs,
        "Redis",
        FakeRedis,
    )

    monkeypatch.setattr(
        jobs,
        "RQQueueProvider",
        RecordingQueueProvider,
    )

    result = jobs.prepare_news_video_jobs(
        limit=5,
        audio_version=1,
        video_version=1,
    )

    assert result["status"] == "processed"
    assert result["candidate_count"] == 1
    assert result["prepared_count"] == 1
    assert result["enqueued_count"] == 1
    assert result["duplicate_count"] == 0

    assert RecordingQueueProvider.calls == [
        {
            "queue_name": QueueName.DEFAULT,
            "function_path": ("project_g.interfaces.workers.jobs.process_news_video"),
            "args": (str(_VIDEO_ID), 1),
            "kwargs": None,
            "job_id": f"news-video-{_VIDEO_ID}-a1",
            "description": "Generate Project G news video",
        }
    ]

    video, media, audio = _load_states(database_engine)

    assert video.status is NewsVideoGenerationStatus.PENDING
    assert video.attempt_count == 0
    assert video.source_audio_generation_id == _AUDIO_ID
    assert video.source_audio_sha256 == _AUDIO_HASH

    assert media.status is NewsMediaProductionStatus.PROCESSING
    assert audio.status is NewsNarrationAudioStatus.GENERATED
