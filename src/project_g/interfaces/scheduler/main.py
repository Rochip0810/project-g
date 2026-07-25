import signal
from threading import Event
from types import FrameType

from redis import Redis

from project_g.infrastructure.config import get_settings
from project_g.infrastructure.logging import (
    configure_logging,
    get_logger,
)
from project_g.infrastructure.queue import (
    RQQueueProvider,
    create_redis_connection_pool,
)
from project_g.interfaces.scheduler.lock import (
    RedisSchedulerLock,
)
from project_g.interfaces.scheduler.service import (
    SchedulerService,
)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    logger = get_logger("project_g.scheduler")
    stop_event = Event()

    def request_stop(
        signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        logger.info(
            "scheduler_stop_requested",
            event_name="scheduler_stop_requested",
            signal_number=signal_number,
        )
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    queue_provider = RQQueueProvider(
        settings,
        connection,
    )
    scheduler_lock = RedisSchedulerLock(
        connection,
        key=settings.scheduler_lock_key,
        timeout_seconds=(settings.scheduler_lock_timeout_seconds),
    )
    scheduler = SchedulerService(
        settings,
        queue_provider,
        scheduler_lock,
    )

    logger.info(
        "scheduler_started",
        event_name="scheduler_started",
        interval_seconds=(settings.scheduler_interval_seconds),
    )

    try:
        scheduler.run_forever(stop_event)
    finally:
        logger.info(
            "scheduler_stopped",
            event_name="scheduler_stopped",
        )
        connection.close()
