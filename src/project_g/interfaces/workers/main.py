from typing import Any

from redis import Redis
from rq import Worker
from rq.serializers import JSONSerializer

from project_g.infrastructure.config import Settings, get_settings
from project_g.infrastructure.logging import configure_logging, get_logger
from project_g.infrastructure.queue import (
    create_redis_connection_pool,
)
from project_g.infrastructure.queue.rq_provider import RQQueueProvider
from project_g.ports.queue import QueueName


def create_worker(
    settings: Settings,
    connection: Any,
) -> Worker:
    provider = RQQueueProvider(settings, connection)

    queues = [
        provider.get_queue(QueueName.SYSTEM),
        provider.get_queue(QueueName.DEFAULT),
    ]

    return Worker(
        queues,
        connection=connection,
        name=(f"{settings.app_name}-{settings.app_env.value}-worker"),
        serializer=JSONSerializer,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    logger = get_logger("project_g.worker")

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    logger.info(
        "worker_started",
        event_name="worker_started",
        queues=[
            settings.rq_system_queue,
            settings.rq_default_queue,
        ],
    )

    try:
        worker = create_worker(settings, connection)
        worker.work()
    finally:
        logger.info(
            "worker_stopped",
            event_name="worker_stopped",
        )
        connection.close()
