from typing import Any

import pytest
from fakeredis import FakeStrictRedis
from rq.exceptions import DuplicateJobError

from project_g.infrastructure.config import (
    AppEnvironment,
    Settings,
)
from project_g.infrastructure.queue import RQQueueProvider
from project_g.interfaces.workers.jobs import system_heartbeat
from project_g.interfaces.workers.main import create_worker
from project_g.ports.queue import QueueName


def _create_connection() -> Any:
    return FakeStrictRedis(decode_responses=False)


def _create_settings() -> Settings:
    return Settings(
        app_env=AppEnvironment.TEST,
        app_name="project-g-test",
        rq_default_queue="default-test",
        rq_system_queue="system-test",
        rq_job_timeout_seconds=45,
        rq_max_retries=2,
        rq_result_ttl_seconds=120,
        rq_failure_ttl_seconds=600,
    )


def test_default_and_system_queues_are_created() -> None:
    provider = RQQueueProvider(
        _create_settings(),
        _create_connection(),
    )

    assert provider.get_queue(QueueName.DEFAULT).name == ("default-test")
    assert provider.get_queue(QueueName.SYSTEM).name == ("system-test")


def test_heartbeat_job_can_execute_synchronously() -> None:
    provider = RQQueueProvider(
        _create_settings(),
        _create_connection(),
        is_async=False,
    )

    snapshot = provider.enqueue(
        QueueName.SYSTEM,
        "project_g.interfaces.workers.jobs.system_heartbeat",
        kwargs={"source": "unit-test"},
        job_id="heartbeat-test",
    )

    assert snapshot.job_id == "heartbeat-test"
    assert snapshot.queue is QueueName.SYSTEM
    assert snapshot.status == "finished"

    job = provider.get_queue(QueueName.SYSTEM).fetch_job("heartbeat-test")

    assert job is not None

    result = job.return_value()

    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert result["source"] == "unit-test"
    assert "timestamp" in result


def test_job_uses_timeout_retry_and_ttl_settings() -> None:
    settings = _create_settings()
    provider = RQQueueProvider(
        settings,
        _create_connection(),
    )

    provider.enqueue(
        QueueName.DEFAULT,
        "project_g.interfaces.workers.jobs.system_heartbeat",
        job_id="configured-job",
    )

    job = provider.get_queue(QueueName.DEFAULT).fetch_job("configured-job")

    assert job is not None
    assert job.timeout == 45
    assert job.retries_left == 2
    assert job.result_ttl == 120
    assert job.failure_ttl == 600


def test_explicit_job_id_prevents_duplicates() -> None:
    provider = RQQueueProvider(
        _create_settings(),
        _create_connection(),
    )

    provider.enqueue(
        QueueName.DEFAULT,
        "project_g.interfaces.workers.jobs.system_heartbeat",
        job_id="unique-heartbeat",
    )

    with pytest.raises(DuplicateJobError):
        provider.enqueue(
            QueueName.DEFAULT,
            "project_g.interfaces.workers.jobs.system_heartbeat",
            job_id="unique-heartbeat",
        )


def test_queued_job_can_be_cancelled() -> None:
    provider = RQQueueProvider(
        _create_settings(),
        _create_connection(),
    )

    provider.enqueue(
        QueueName.DEFAULT,
        "project_g.interfaces.workers.jobs.system_heartbeat",
        job_id="cancel-heartbeat",
    )

    snapshot = provider.cancel_job(
        QueueName.DEFAULT,
        "cancel-heartbeat",
    )

    assert snapshot is not None
    assert snapshot.status == "canceled"


def test_missing_job_returns_none() -> None:
    provider = RQQueueProvider(
        _create_settings(),
        _create_connection(),
    )

    assert (
        provider.get_job(
            QueueName.DEFAULT,
            "missing-job",
        )
        is None
    )

    assert (
        provider.cancel_job(
            QueueName.DEFAULT,
            "missing-job",
        )
        is None
    )


def test_system_heartbeat_returns_structured_data() -> None:
    result = system_heartbeat("direct-test")

    assert result["status"] == "ok"
    assert result["source"] == "direct-test"
    assert "timestamp" in result


def test_worker_listens_to_system_queue_first() -> None:
    settings = _create_settings()
    connection = _create_connection()

    worker = create_worker(settings, connection)

    assert [queue.name for queue in worker.queues] == [
        "system-test",
        "default-test",
    ]
    assert worker.name == "project-g-test-test-worker"
