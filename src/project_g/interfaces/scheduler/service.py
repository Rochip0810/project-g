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

HOCHI_DISCOVERY_INTERVAL_SECONDS = 300
RELEVANCE_RECOVERY_INTERVAL_SECONDS = 300
RELEVANCE_RECOVERY_LIMIT = 5


class SchedulerRunStatus(StrEnum):
    ENQUEUED = "enqueued"
    SKIPPED_LOCKED = "skipped_locked"
    SKIPPED_DUPLICATE = "skipped_duplicate"


@dataclass(frozen=True, slots=True)
class SchedulerIterationResult:
    status: SchedulerRunStatus
    job_id: str | None
    discovery_job_id: str | None = None
    hochi_discovery_job_id: str | None = None
    relevance_recovery_job_id: str | None = None


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

    @staticmethod
    def _time_bucket(
        current_time: datetime,
        *,
        interval_seconds: int,
    ) -> int:
        return int(current_time.timestamp()) // interval_seconds

    def _create_heartbeat_job_id(
        self,
        current_time: datetime,
    ) -> str:
        bucket = self._time_bucket(
            current_time,
            interval_seconds=(self._settings.scheduler_interval_seconds),
        )
        return f"system-heartbeat-{bucket}"

    def _create_discovery_job_id(
        self,
        current_time: datetime,
    ) -> str:
        bucket = self._time_bucket(
            current_time,
            interval_seconds=(self._settings.scheduler_interval_seconds),
        )
        return f"news-discovery-giants-{bucket}"

    def _create_hochi_discovery_job_id(
        self,
        current_time: datetime,
    ) -> str:
        bucket = self._time_bucket(
            current_time,
            interval_seconds=(HOCHI_DISCOVERY_INTERVAL_SECONDS),
        )
        return f"news-discovery-hochi-{bucket}"

    def _create_relevance_recovery_job_id(
        self,
        current_time: datetime,
    ) -> str:
        bucket = self._time_bucket(
            current_time,
            interval_seconds=(RELEVANCE_RECOVERY_INTERVAL_SECONDS),
        )
        return f"news-relevance-recovery-{bucket}"

    def run_once(self) -> SchedulerIterationResult:
        if not self._scheduler_lock.acquire():
            return SchedulerIterationResult(
                status=SchedulerRunStatus.SKIPPED_LOCKED,
                job_id=None,
                discovery_job_id=None,
                hochi_discovery_job_id=None,
                relevance_recovery_job_id=None,
            )

        try:
            current_time = self._clock()

            heartbeat_job_id = self._create_heartbeat_job_id(current_time)
            discovery_job_id = self._create_discovery_job_id(current_time)
            hochi_discovery_job_id = self._create_hochi_discovery_job_id(current_time)
            relevance_recovery_job_id = self._create_relevance_recovery_job_id(current_time)

            enqueued_any = False

            try:
                self._queue_provider.enqueue(
                    QueueName.SYSTEM,
                    ("project_g.interfaces.workers.jobs.system_heartbeat"),
                    kwargs={"source": "scheduler"},
                    job_id=heartbeat_job_id,
                    description=("Project G system heartbeat"),
                )
            except DuplicateJobError:
                pass
            else:
                enqueued_any = True

            try:
                self._queue_provider.enqueue(
                    QueueName.DEFAULT,
                    ("project_g.interfaces.workers.jobs.discover_giants_news"),
                    job_id=discovery_job_id,
                    description="Discover Giants news",
                )
            except DuplicateJobError:
                pass
            else:
                enqueued_any = True

            try:
                self._queue_provider.enqueue(
                    QueueName.DEFAULT,
                    ("project_g.interfaces.workers.jobs.discover_hochi_giants_news"),
                    kwargs={"max_items": 5},
                    job_id=hochi_discovery_job_id,
                    description=("Discover Sports Hochi Giants news"),
                )
            except DuplicateJobError:
                pass
            else:
                enqueued_any = True

            try:
                self._queue_provider.enqueue(
                    QueueName.DEFAULT,
                    ("project_g.interfaces.workers.jobs.recover_pending_news_relevance"),
                    kwargs={
                        "limit": RELEVANCE_RECOVERY_LIMIT,
                    },
                    job_id=relevance_recovery_job_id,
                    description=("Recover pending news relevance analyses"),
                )
            except DuplicateJobError:
                pass
            else:
                enqueued_any = True

            return SchedulerIterationResult(
                status=(
                    SchedulerRunStatus.ENQUEUED
                    if enqueued_any
                    else SchedulerRunStatus.SKIPPED_DUPLICATE
                ),
                job_id=heartbeat_job_id,
                discovery_job_id=discovery_job_id,
                hochi_discovery_job_id=(hochi_discovery_job_id),
                relevance_recovery_job_id=(relevance_recovery_job_id),
            )
        finally:
            self._scheduler_lock.release()

    def run_forever(
        self,
        stop_event: Event,
    ) -> None:
        while not stop_event.is_set():
            result = self.run_once()

            self._logger.info(
                "scheduler_iteration_completed",
                event_name=("scheduler_iteration_completed"),
                status=result.status.value,
                job_id=result.job_id,
                discovery_job_id=(result.discovery_job_id),
                hochi_discovery_job_id=(result.hochi_discovery_job_id),
                relevance_recovery_job_id=(result.relevance_recovery_job_id),
            )

            stop_event.wait(self._settings.scheduler_interval_seconds)
