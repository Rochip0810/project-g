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


class FailingMediaQueueProvider(FakeQueueProvider):
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
        if function_path == (
            "project_g.interfaces.workers.jobs.create_news_media_production_intakes"
        ):
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


def test_scheduler_enqueues_media_production_orchestration() -> None:
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
        == ("project_g.interfaces.workers.jobs.create_news_media_production_intakes")
    ]

    assert calls == [
        {
            "queue_name": QueueName.DEFAULT,
            "function_path": (
                "project_g.interfaces.workers.jobs.create_news_media_production_intakes"
            ),
            "args": (),
            "kwargs": {
                "limit": 5,
                "media_version": 1,
            },
            "job_id": "news-media-production-5962896",
            "description": ("Create news media production intakes"),
        }
    ]

    assert result.status is SchedulerRunStatus.ENQUEUED
    assert result.media_production_job_id == ("news-media-production-5962896")
    assert scheduler_lock.released is True


def test_media_production_job_id_uses_five_minute_bucket() -> None:
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

    assert first.media_production_job_id == second.media_production_job_id
    assert third.media_production_job_id != first.media_production_job_id


def test_media_queue_failure_propagates_and_releases_lock() -> None:
    queue_provider = FailingMediaQueueProvider()
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
