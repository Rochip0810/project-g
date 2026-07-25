from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event

from rq.exceptions import DuplicateJobError

from project_g.infrastructure.config import Settings
from project_g.infrastructure.logging import get_logger
from project_g.infrastructure.queue import RQQueueProvider
from project_g.interfaces.scheduler.lock import SchedulerLock
from project_g.ports.queue import QueueName

Clock = Callable[[], datetime]


class SchedulerRunStatus(StrEnum):
    ENQUEUED = "enqueued"
    SKIPPED_LOCKED = "skipped_locked"
    SKIPPED_DUPLICATE = "skipped_duplicate"


@dataclass(frozen=True, slots=True)
class SchedulerIterationResult:
    status: SchedulerRunStatus
    job_id: str | None


class SchedulerService:
    def __init__(
        self,
        settings: Settings,
        queue_provider: RQQueueProvider,
        scheduler_lock: SchedulerLock,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._queue_provider = queue_provider
        self._scheduler_lock = scheduler_lock
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._logger = get_logger("project_g.scheduler")

    def _create_heartbeat_job_id(
        self,
        current_time: datetime,
    ) -> str:
        interval = self._settings.scheduler_interval_seconds
        time_bucket = int(current_time.timestamp()) // interval

        return f"system-heartbeat-{time_bucket}"

    def run_once(self) -> SchedulerIterationResult:
        if not self._scheduler_lock.acquire():
            return SchedulerIterationResult(
                status=SchedulerRunStatus.SKIPPED_LOCKED,
                job_id=None,
            )

        try:
            job_id = self._create_heartbeat_job_id(self._clock())

            try:
                self._queue_provider.enqueue(
                    QueueName.SYSTEM,
                    ("project_g.interfaces.workers.jobs.system_heartbeat"),
                    kwargs={"source": "scheduler"},
                    job_id=job_id,
                    description="Project G system heartbeat",
                )
            except DuplicateJobError:
                return SchedulerIterationResult(
                    status=(SchedulerRunStatus.SKIPPED_DUPLICATE),
                    job_id=job_id,
                )

            return SchedulerIterationResult(
                status=SchedulerRunStatus.ENQUEUED,
                job_id=job_id,
            )
        finally:
            self._scheduler_lock.release()

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            result = self.run_once()

            self._logger.info(
                "scheduler_iteration_completed",
                event_name="scheduler_iteration_completed",
                status=result.status.value,
                job_id=result.job_id,
            )

            stop_event.wait(self._settings.scheduler_interval_seconds)
