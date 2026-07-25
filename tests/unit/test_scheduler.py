from datetime import UTC, datetime
from threading import Event
from typing import Any
from unittest.mock import MagicMock

from fakeredis import FakeStrictRedis

from project_g.infrastructure.config import (
    AppEnvironment,
    Settings,
)
from project_g.infrastructure.queue import RQQueueProvider
from project_g.interfaces.scheduler import (
    RedisSchedulerLock,
    SchedulerRunStatus,
    SchedulerService,
)
from project_g.ports.queue import QueueName


class AvailableLock:
    def __init__(self) -> None:
        self.acquire_count = 0
        self.release_count = 0

    def acquire(self) -> bool:
        self.acquire_count += 1
        return True

    def release(self) -> None:
        self.release_count += 1


class UnavailableLock:
    def acquire(self) -> bool:
        return False

    def release(self) -> None:
        raise AssertionError("Unavailable lock must not be released")


def _create_connection() -> Any:
    return FakeStrictRedis(decode_responses=False)


def _create_settings() -> Settings:
    return Settings(
        app_env=AppEnvironment.TEST,
        app_name="project-g-test",
        rq_default_queue="default-test",
        rq_system_queue="system-test",
        scheduler_interval_seconds=60,
        scheduler_lock_timeout_seconds=30,
        scheduler_lock_key="project-g-test:scheduler:lock",
    )


def _fixed_clock() -> datetime:
    return datetime(
        2026,
        7,
        25,
        12,
        0,
        30,
        tzinfo=UTC,
    )


def test_scheduler_enqueues_heartbeat_into_system_queue() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )
    scheduler_lock = AvailableLock()

    scheduler = SchedulerService(
        settings,
        provider,
        scheduler_lock,
        clock=_fixed_clock,
    )

    result = scheduler.run_once()

    assert result.status is SchedulerRunStatus.ENQUEUED
    assert result.job_id is not None

    job = provider.get_queue(QueueName.SYSTEM).fetch_job(result.job_id)

    assert job is not None
    assert job.kwargs == {"source": "scheduler"}
    assert scheduler_lock.acquire_count == 1
    assert scheduler_lock.release_count == 1


def test_unavailable_lock_prevents_job_registration() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )

    scheduler = SchedulerService(
        settings,
        provider,
        UnavailableLock(),
        clock=_fixed_clock,
    )

    result = scheduler.run_once()

    assert result.status is SchedulerRunStatus.SKIPPED_LOCKED
    assert result.job_id is None
    assert provider.get_queue(QueueName.SYSTEM).count == 0


def test_deterministic_job_id_prevents_duplicates() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )
    scheduler_lock = AvailableLock()

    scheduler = SchedulerService(
        settings,
        provider,
        scheduler_lock,
        clock=_fixed_clock,
    )

    first_result = scheduler.run_once()
    second_result = scheduler.run_once()

    assert first_result.status is SchedulerRunStatus.ENQUEUED
    assert second_result.status is SchedulerRunStatus.SKIPPED_DUPLICATE
    assert first_result.job_id == second_result.job_id
    assert provider.get_queue(QueueName.SYSTEM).count == 1


def test_next_time_bucket_creates_new_job_id() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )
    scheduler_lock = AvailableLock()

    times = iter(
        [
            datetime(
                2026,
                7,
                25,
                12,
                0,
                30,
                tzinfo=UTC,
            ),
            datetime(
                2026,
                7,
                25,
                12,
                1,
                30,
                tzinfo=UTC,
            ),
        ]
    )

    scheduler = SchedulerService(
        settings,
        provider,
        scheduler_lock,
        clock=lambda: next(times),
    )

    first_result = scheduler.run_once()
    second_result = scheduler.run_once()

    assert first_result.job_id != second_result.job_id
    assert provider.get_queue(QueueName.SYSTEM).count == 2


def test_run_forever_stops_when_event_is_already_set() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )

    scheduler = SchedulerService(
        settings,
        provider,
        AvailableLock(),
        clock=_fixed_clock,
    )

    stop_event = Event()
    stop_event.set()

    scheduler.run_forever(stop_event)

    assert provider.get_queue(QueueName.SYSTEM).count == 0


def test_redis_scheduler_lock_uses_non_blocking_lock() -> None:
    connection = MagicMock()
    redis_lock = MagicMock()
    redis_lock.acquire.return_value = True
    connection.lock.return_value = redis_lock

    scheduler_lock = RedisSchedulerLock(
        connection,
        key="project-g:scheduler:lock",
        timeout_seconds=30,
    )

    assert scheduler_lock.acquire() is True

    connection.lock.assert_called_once_with(
        name="project-g:scheduler:lock",
        timeout=30,
        blocking_timeout=0,
    )
    redis_lock.acquire.assert_called_once_with(blocking=False)

    scheduler_lock.release()

    redis_lock.release.assert_called_once_with()


def test_scheduler_entrypoint_can_be_imported() -> None:
    from project_g.interfaces.scheduler import main

    assert callable(main)
