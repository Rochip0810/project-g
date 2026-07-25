from collections.abc import Mapping, Sequence
from typing import Any

from rq import Queue, Retry
from rq.job import Job
from rq.serializers import JSONSerializer

from project_g.infrastructure.config import Settings
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)


class RQQueueProvider:
    def __init__(
        self,
        settings: Settings,
        connection: Any,
        *,
        is_async: bool = True,
    ) -> None:
        self._settings = settings
        self._connection = connection
        self._queues: dict[QueueName, Queue] = {
            QueueName.DEFAULT: self._create_queue(
                settings.rq_default_queue,
                is_async=is_async,
            ),
            QueueName.SYSTEM: self._create_queue(
                settings.rq_system_queue,
                is_async=is_async,
            ),
        }

    def _create_queue(
        self,
        name: str,
        *,
        is_async: bool,
    ) -> Queue:
        return Queue(
            name=name,
            connection=self._connection,
            default_timeout=self._settings.rq_job_timeout_seconds,
            is_async=is_async,
            serializer=JSONSerializer,
        )

    def get_queue(self, queue_name: QueueName) -> Queue:
        return self._queues[queue_name]

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
        queue = self.get_queue(queue_name)

        retry = (
            Retry(max=self._settings.rq_max_retries) if self._settings.rq_max_retries > 0 else None
        )

        job = queue.enqueue(
            function_path,
            args=tuple(args),
            kwargs=dict(kwargs or {}),
            job_id=job_id,
            unique=job_id is not None,
            job_timeout=self._settings.rq_job_timeout_seconds,
            result_ttl=self._settings.rq_result_ttl_seconds,
            failure_ttl=self._settings.rq_failure_ttl_seconds,
            retry=retry,
            description=description,
        )

        return self._to_snapshot(job, queue_name)

    def get_job(
        self,
        queue_name: QueueName,
        job_id: str,
    ) -> JobSnapshot | None:
        job = self.get_queue(queue_name).fetch_job(job_id)

        if job is None:
            return None

        return self._to_snapshot(job, queue_name)

    def cancel_job(
        self,
        queue_name: QueueName,
        job_id: str,
    ) -> JobSnapshot | None:
        job = self.get_queue(queue_name).fetch_job(job_id)

        if job is None:
            return None

        job.cancel()

        return self._to_snapshot(job, queue_name)

    @staticmethod
    def _to_snapshot(
        job: Job,
        queue_name: QueueName,
    ) -> JobSnapshot:
        status = job.get_status(refresh=True)
        status_value = status.value if status is not None else "unknown"

        return JobSnapshot(
            job_id=job.id,
            queue=queue_name,
            status=status_value,
        )
