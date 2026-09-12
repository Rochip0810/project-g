from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from rq.exceptions import DuplicateJobError
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
from project_g.interfaces.workers import jobs
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_BASE_TIME = datetime(
    2026,
    9,
    12,
    11,
    0,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("67b60854-60ef-41d7-8fca-018606510101")
_SCRIPT_ID = UUID("67b60854-60ef-41d7-8fca-018606510201")
_MEDIA_ID = UUID("67b60854-60ef-41d7-8fca-018606510301")


class FakeSettings:
    rq_job_timeout_seconds = 180
    openai_tts_model = "gpt-4o-mini-tts"
    openai_tts_voice = "marin"
    openai_tts_format = "mp3"


class FakePool:
    def close(self) -> None:
        pass


class FakeConnection:
    def close(self) -> None:
        pass


class FakeRedis:
    @staticmethod
    def from_pool(_: object) -> FakeConnection:
        return FakeConnection()


class RecordingQueueProvider:
    seen_job_ids: ClassVar[set[str]] = set()
    calls: ClassVar[list[dict[str, object]]] = []

    def __init__(
        self,
        _: object,
        __: object,
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

        if job_id in self.seen_job_ids:
            raise DuplicateJobError

        self.seen_job_ids.add(job_id)

        self.calls.append(
            {
                "queue_name": queue_name,
                "function_path": function_path,
                "args": tuple(args),
                "job_id": job_id,
                "description": description,
            }
        )

        return JobSnapshot(
            job_id=job_id,
            queue=queue_name,
            status="queued",
        )


class FailingQueueProvider(RecordingQueueProvider):
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
        raise RuntimeError("queue unavailable")


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


def _script() -> NewsScriptGeneration:
    evidence = (
        NewsScriptEvidenceSnapshot(
            text="確認済みのテスト事実。",
            source_id="npb_official",
            source_url="https://npb.jp/example/",
            competition_level=CompetitionLevel.FIRST_TEAM,
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
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
        .record_generated(
            hook="巨人の最新ニュースです。",
            main_narration="事実を伝える本文です。",
            project_g_comment="ここはしっかり見たいところやな。",
            closing="今後にも注目です。",
            full_narration="完成したProject Gナレーション",
            evidence_snapshot=evidence,
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
    )


def _media() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_MEDIA_ID,
        script_generation_id=_SCRIPT_ID,
        media_version=1,
        created_at=_BASE_TIME + timedelta(minutes=3),
    )


def _seed(
    engine: Engine,
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


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    queue_provider: type[RecordingQueueProvider],
) -> None:
    monkeypatch.setattr(
        jobs,
        "Settings",
        FakeSettings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _: engine,
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
        queue_provider,
    )


def test_worker_persists_audio_before_enqueue_and_is_idempotent(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )
    _seed(database_engine)

    RecordingQueueProvider.seen_job_ids = set()
    RecordingQueueProvider.calls = []

    _patch_common(
        monkeypatch,
        database_engine,
        RecordingQueueProvider,
    )

    first = jobs.prepare_news_narration_audio_jobs(
        limit=5,
        audio_version=1,
    )
    second = jobs.prepare_news_narration_audio_jobs(
        limit=5,
        audio_version=1,
    )

    assert first["status"] == "processed"
    assert first["candidate_count"] == 1
    assert first["prepared_count"] == 1
    assert first["enqueued_count"] == 1
    assert first["duplicate_count"] == 0

    assert second["candidate_count"] == 1
    assert second["prepared_count"] == 1
    assert second["enqueued_count"] == 0
    assert second["duplicate_count"] == 1

    assert len(RecordingQueueProvider.calls) == 1

    call = RecordingQueueProvider.calls[0]

    assert call["queue_name"] is QueueName.DEFAULT
    assert call["function_path"] == (
        "project_g.interfaces.workers.jobs.process_news_narration_audio"
    )
    assert call["job_id"] is not None
    assert str(call["job_id"]).endswith("-a1")

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        generation = SqlAlchemyNewsNarrationAudioGenerationRepository(
            session
        ).get_by_media_production_version(
            media_production_id=_MEDIA_ID,
            audio_version=1,
        )

        media = SqlAlchemyNewsMediaProductionRepository(session).get_by_media_production_id(
            _MEDIA_ID
        )

    assert generation is not None
    assert generation.status.value == "pending"
    assert generation.attempt_count == 0

    assert media is not None
    assert media.status.value == "pending"
    assert media.attempt_count == 0


def test_queue_failure_keeps_durable_pending_audio(
    alembic_config: Config,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(
        alembic_config,
        "head",
    )
    _seed(database_engine)

    _patch_common(
        monkeypatch,
        database_engine,
        FailingQueueProvider,
    )

    with pytest.raises(
        RuntimeError,
        match="queue unavailable",
    ):
        jobs.prepare_news_narration_audio_jobs(
            limit=5,
            audio_version=1,
        )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        generation = SqlAlchemyNewsNarrationAudioGenerationRepository(
            session
        ).get_by_media_production_version(
            media_production_id=_MEDIA_ID,
            audio_version=1,
        )

    assert generation is not None
    assert generation.status.value == "pending"
    assert generation.attempt_count == 0


@pytest.mark.parametrize(
    ("limit", "audio_version"),
    (
        (0, 1),
        (51, 1),
        (5, 0),
    ),
)
def test_worker_rejects_invalid_options_before_database_setup(
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    audio_version: int,
) -> None:
    def unexpected_settings() -> FakeSettings:
        raise AssertionError("Settings must not be constructed")

    monkeypatch.setattr(
        jobs,
        "Settings",
        unexpected_settings,
    )

    with pytest.raises(ValueError):
        jobs.prepare_news_narration_audio_jobs(
            limit=limit,
            audio_version=audio_version,
        )
