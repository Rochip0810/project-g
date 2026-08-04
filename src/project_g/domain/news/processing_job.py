from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_ERROR_LENGTH = 2000


class NewsProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class InvalidNewsProcessingJobError(ValueError):
    """Raised when processing-job data is inconsistent."""


class InvalidNewsProcessingTransitionError(RuntimeError):
    """Raised when a processing-job transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsProcessingJobError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class NewsProcessingJob:
    job_id: UUID
    intake_id: UUID
    status: NewsProcessingStatus
    attempt_count: int
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        job_id: UUID,
        intake_id: UUID,
        created_at: datetime,
    ) -> "NewsProcessingJob":
        return cls(
            job_id=job_id,
            intake_id=intake_id,
            status=NewsProcessingStatus.PENDING,
            attempt_count=0,
            last_error=None,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            updated_at=created_at,
        )

    def start(
        self,
        *,
        started_at: datetime,
    ) -> "NewsProcessingJob":
        if self.status is not NewsProcessingStatus.PENDING:
            raise InvalidNewsProcessingTransitionError(
                f"Cannot start a job with status {self.status.value}"
            )

        return replace(
            self,
            status=NewsProcessingStatus.PROCESSING,
            attempt_count=self.attempt_count + 1,
            last_error=None,
            started_at=started_at,
            completed_at=None,
            updated_at=started_at,
        )

    def complete(
        self,
        *,
        completed_at: datetime,
    ) -> "NewsProcessingJob":
        if self.status is not NewsProcessingStatus.PROCESSING:
            raise InvalidNewsProcessingTransitionError(
                f"Cannot complete a job with status {self.status.value}"
            )

        return replace(
            self,
            status=NewsProcessingStatus.COMPLETED,
            last_error=None,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def fail(
        self,
        *,
        error: str,
        completed_at: datetime,
    ) -> "NewsProcessingJob":
        if self.status is not NewsProcessingStatus.PROCESSING:
            raise InvalidNewsProcessingTransitionError(
                f"Cannot fail a job with status {self.status.value}"
            )

        normalized_error = error.strip()

        if not normalized_error:
            raise InvalidNewsProcessingJobError("error must not be empty")

        if len(normalized_error) > _MAX_ERROR_LENGTH:
            raise InvalidNewsProcessingJobError(
                f"error must not exceed {_MAX_ERROR_LENGTH} characters"
            )

        return replace(
            self,
            status=NewsProcessingStatus.FAILED,
            last_error=normalized_error,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def __post_init__(self) -> None:
        _require_aware(
            self.created_at,
            field_name="created_at",
        )
        _require_aware(
            self.updated_at,
            field_name="updated_at",
        )

        if self.started_at is not None:
            _require_aware(
                self.started_at,
                field_name="started_at",
            )

        if self.completed_at is not None:
            _require_aware(
                self.completed_at,
                field_name="completed_at",
            )

        if self.attempt_count < 0:
            raise InvalidNewsProcessingJobError("attempt_count must not be negative")

        if self.updated_at < self.created_at:
            raise InvalidNewsProcessingJobError("updated_at must not be earlier than created_at")

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidNewsProcessingJobError("started_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise InvalidNewsProcessingJobError("completed_at must not be earlier than started_at")

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsProcessingStatus.PENDING:
            if (
                self.attempt_count != 0
                or self.started_at is not None
                or self.completed_at is not None
                or self.last_error is not None
            ):
                raise InvalidNewsProcessingJobError("pending job fields are inconsistent")
            return

        if self.attempt_count < 1:
            raise InvalidNewsProcessingJobError("started jobs must have at least one attempt")

        if self.started_at is None:
            raise InvalidNewsProcessingJobError("started jobs must include started_at")

        if self.status is NewsProcessingStatus.PROCESSING:
            if self.completed_at is not None or self.last_error is not None:
                raise InvalidNewsProcessingJobError("processing job fields are inconsistent")
            return

        if self.completed_at is None:
            raise InvalidNewsProcessingJobError("finished jobs must include completed_at")

        if self.status is NewsProcessingStatus.COMPLETED:
            if self.last_error is not None:
                raise InvalidNewsProcessingJobError("completed jobs must not include last_error")
            return

        if self.last_error is None or not self.last_error.strip():
            raise InvalidNewsProcessingJobError("failed jobs must include last_error")
