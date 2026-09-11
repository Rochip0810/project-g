from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_FAILURE_REASON_LENGTH = 2000


class NewsMediaProductionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class InvalidNewsMediaProductionError(ValueError):
    """Raised when media-production data is inconsistent."""


class InvalidNewsMediaProductionTransitionError(RuntimeError):
    """Raised when a media-production transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsMediaProductionError(f"{field_name} must be timezone-aware")


def _normalize_failure_reason(
    value: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise InvalidNewsMediaProductionError("failure_reason must not be empty")

    if len(normalized) > _MAX_FAILURE_REASON_LENGTH:
        raise InvalidNewsMediaProductionError(
            f"failure_reason must not exceed {_MAX_FAILURE_REASON_LENGTH} characters"
        )

    return normalized


@dataclass(frozen=True, slots=True)
class NewsMediaProduction:
    media_production_id: UUID
    script_generation_id: UUID
    media_version: int
    status: NewsMediaProductionStatus
    attempt_count: int
    failure_reason: str | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        media_production_id: UUID,
        script_generation_id: UUID,
        media_version: int,
        created_at: datetime,
    ) -> "NewsMediaProduction":
        return cls(
            media_production_id=media_production_id,
            script_generation_id=script_generation_id,
            media_version=media_version,
            status=NewsMediaProductionStatus.PENDING,
            attempt_count=0,
            failure_reason=None,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            updated_at=created_at,
        )

    def start(
        self,
        *,
        started_at: datetime,
    ) -> "NewsMediaProduction":
        if self.status not in {
            NewsMediaProductionStatus.PENDING,
            NewsMediaProductionStatus.FAILED,
        }:
            raise InvalidNewsMediaProductionTransitionError(
                "Media production can only start from pending or failed"
            )

        if started_at < self.updated_at:
            raise InvalidNewsMediaProductionError("started_at must not be earlier than updated_at")

        return replace(
            self,
            status=NewsMediaProductionStatus.PROCESSING,
            attempt_count=self.attempt_count + 1,
            failure_reason=None,
            started_at=started_at,
            completed_at=None,
            updated_at=started_at,
        )

    def mark_ready(
        self,
        *,
        completed_at: datetime,
    ) -> "NewsMediaProduction":
        self._require_processing()

        return replace(
            self,
            status=NewsMediaProductionStatus.READY,
            failure_reason=None,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        completed_at: datetime,
    ) -> "NewsMediaProduction":
        self._require_processing()

        return replace(
            self,
            status=NewsMediaProductionStatus.FAILED,
            failure_reason=_normalize_failure_reason(reason),
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def _require_processing(self) -> None:
        if self.status is not NewsMediaProductionStatus.PROCESSING:
            raise InvalidNewsMediaProductionTransitionError("Media production must be processing")

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

        if self.media_version < 1:
            raise InvalidNewsMediaProductionError("media_version must be at least 1")

        if self.attempt_count < 0:
            raise InvalidNewsMediaProductionError("attempt_count must not be negative")

        if self.updated_at < self.created_at:
            raise InvalidNewsMediaProductionError("updated_at must not be earlier than created_at")

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidNewsMediaProductionError("started_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise InvalidNewsMediaProductionError(
                "completed_at must not be earlier than started_at"
            )

        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _normalize_failure_reason(self.failure_reason),
            )

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsMediaProductionStatus.PENDING:
            self._validate_pending()
            return

        if self.attempt_count < 1:
            raise InvalidNewsMediaProductionError(
                "started media production must have at least one attempt"
            )

        if self.started_at is None:
            raise InvalidNewsMediaProductionError(
                "started media production must include started_at"
            )

        if self.status is NewsMediaProductionStatus.PROCESSING:
            self._validate_processing()
            return

        if self.completed_at is None:
            raise InvalidNewsMediaProductionError(
                "finished media production must include completed_at"
            )

        if self.status is NewsMediaProductionStatus.READY:
            self._validate_ready()
            return

        self._validate_failed()

    def _validate_pending(self) -> None:
        if (
            self.attempt_count != 0
            or self.failure_reason is not None
            or self.started_at is not None
            or self.completed_at is not None
        ):
            raise InvalidNewsMediaProductionError(
                "pending media production fields are inconsistent"
            )

    def _validate_processing(self) -> None:
        if self.failure_reason is not None or self.completed_at is not None:
            raise InvalidNewsMediaProductionError(
                "processing media production fields are inconsistent"
            )

    def _validate_ready(self) -> None:
        if self.failure_reason is not None:
            raise InvalidNewsMediaProductionError(
                "ready media production must not include failure_reason"
            )

    def _validate_failed(self) -> None:
        if self.failure_reason is None:
            raise InvalidNewsMediaProductionError(
                "failed media production must include failure_reason"
            )
