from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

import pytest

from project_g.infrastructure.config import Settings
from project_g.infrastructure.queue import RQQueueProvider
from project_g.interfaces.scheduler.service import (
    SchedulerRunStatus,
    SchedulerService,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_NOW = datetime(2026, 9, 8, 12, 3, tzinfo=UTC)


class FakeSettings:
    scheduler_interval_seconds = 60


class FakeLock:
    def __init__(self) -> None:
        self.released = False

    def acquire(self) -> bool:
        return True

    def release(self) -> None:
        self.released = True


class FakeQueueProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "queue_name": queue_name,
                "function_path": function_path,
                "args": tuple(args),
                "kwargs": (dict(kwargs) if kwargs is not None else None),
                "job_id": job_id,
                "description": description,
            }
        )

        assert job_id is not None

        return JobSnapshot(
            job_id=job_id,
            queue=queue_name,
            status="queued",
        )


class FailingNarrationQueueProvider(FakeQueueProvider):
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
        if function_path == ("project_g.interfaces.workers.jobs.prepare_news_narration_audio_jobs"):
            raise RuntimeError("queue unavailable")

        return super().enqueue(
            queue_name,
            function_path,
            args=args,
            kwargs=kwargs,
            job_id=job_id,
            description=description,
        )


def _service(
    queue_provider: FakeQueueProvider,
    lock: FakeLock,
    *,
    clock: Callable[[], datetime],
) -> SchedulerService:
    return SchedulerService(
        settings=cast(Settings, FakeSettings()),
        queue_provider=cast(
            RQQueueProvider,
            queue_provider,
        ),
        scheduler_lock=lock,
        clock=clock,
    )


def test_scheduler_enqueues_narration_audio_orchestration() -> None:
    queue_provider = FakeQueueProvider()
    scheduler_lock = FakeLock()

    service = _service(
        queue_provider,
        scheduler_lock,
        clock=lambda: _NOW,
    )

    result = service.run_once()

    calls = [
        call
        for call in queue_provider.calls
        if call["function_path"]
        == ("project_g.interfaces.workers.jobs.prepare_news_narration_audio_jobs")
    ]

    assert calls == [
        {
            "queue_name": QueueName.DEFAULT,
            "function_path": (
                "project_g.interfaces.workers.jobs.prepare_news_narration_audio_jobs"
            ),
            "args": (),
            "kwargs": {
                "limit": 5,
                "audio_version": 1,
            },
            "job_id": ("news-narration-audio-prepare-5962896"),
            "description": "Prepare narration audio jobs",
        }
    ]

    assert result.status is SchedulerRunStatus.ENQUEUED
    assert result.narration_audio_job_id == ("news-narration-audio-prepare-5962896")
    assert scheduler_lock.released is True


def test_narration_audio_job_id_uses_five_minute_bucket() -> None:
    queue_provider = FakeQueueProvider()
    scheduler_lock = FakeLock()

    times = iter(
        (
            datetime(
                2026,
                9,
                8,
                12,
                3,
                tzinfo=UTC,
            ),
            datetime(
                2026,
                9,
                8,
                12,
                4,
                tzinfo=UTC,
            ),
            datetime(
                2026,
                9,
                8,
                12,
                5,
                tzinfo=UTC,
            ),
        )
    )

    service = _service(
        queue_provider,
        scheduler_lock,
        clock=lambda: next(times),
    )

    first = service.run_once()
    second = service.run_once()
    third = service.run_once()

    assert first.narration_audio_job_id == second.narration_audio_job_id
    assert third.narration_audio_job_id != first.narration_audio_job_id


def test_narration_audio_queue_failure_propagates_and_releases_lock() -> None:
    queue_provider = FailingNarrationQueueProvider()
    scheduler_lock = FakeLock()

    service = _service(
        queue_provider,
        scheduler_lock,
        clock=lambda: _NOW,
    )

    with pytest.raises(
        RuntimeError,
        match="queue unavailable",
    ):
        service.run_once()

    assert scheduler_lock.released is True
