from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_REASON_LENGTH = 2000
_MAX_FAILURE_REASON_LENGTH = 1000


class NewsPriorityStatus(StrEnum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    FAILED = "failed"


class InvalidNewsPriorityAnalysisError(ValueError):
    """Raised when priority-analysis data is inconsistent."""


class InvalidNewsPriorityTransitionError(RuntimeError):
    """Raised when a priority-analysis transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsPriorityAnalysisError(f"{field_name} must be timezone-aware")


def _normalize_optional_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if len(normalized) > max_length:
        raise InvalidNewsPriorityAnalysisError(
            f"{field_name} must not exceed {max_length} characters"
        )

    return normalized


@dataclass(frozen=True, slots=True)
class NewsPriorityAnalysis:
    analysis_id: UUID
    intake_id: UUID
    status: NewsPriorityStatus
    priority_score: int | None
    reason: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        analysis_id: UUID,
        intake_id: UUID,
        created_at: datetime,
    ) -> "NewsPriorityAnalysis":
        return cls(
            analysis_id=analysis_id,
            intake_id=intake_id,
            status=NewsPriorityStatus.PENDING,
            priority_score=None,
            reason=None,
            failure_reason=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def record_analyzed(
        self,
        *,
        priority_score: int,
        reason: str,
        updated_at: datetime,
    ) -> "NewsPriorityAnalysis":
        self._require_pending()

        return replace(
            self,
            status=NewsPriorityStatus.ANALYZED,
            priority_score=priority_score,
            reason=reason,
            failure_reason=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        updated_at: datetime,
    ) -> "NewsPriorityAnalysis":
        self._require_pending()

        return replace(
            self,
            status=NewsPriorityStatus.FAILED,
            priority_score=None,
            reason=None,
            failure_reason=reason,
            updated_at=updated_at,
        )

    def _require_pending(self) -> None:
        if self.status is not NewsPriorityStatus.PENDING:
            raise InvalidNewsPriorityTransitionError(
                "Priority analysis can only transition from pending"
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

        if self.updated_at < self.created_at:
            raise InvalidNewsPriorityAnalysisError("updated_at must not be earlier than created_at")

        if self.priority_score is not None and not 0 <= self.priority_score <= 100:
            raise InvalidNewsPriorityAnalysisError("priority_score must be between 0 and 100")

        normalized_reason = _normalize_optional_text(
            self.reason,
            field_name="reason",
            max_length=_MAX_REASON_LENGTH,
        )
        normalized_failure_reason = _normalize_optional_text(
            self.failure_reason,
            field_name="failure_reason",
            max_length=_MAX_FAILURE_REASON_LENGTH,
        )

        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )
        object.__setattr__(
            self,
            "failure_reason",
            normalized_failure_reason,
        )

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsPriorityStatus.PENDING:
            if (
                self.priority_score is not None
                or self.reason is not None
                or self.failure_reason is not None
            ):
                raise InvalidNewsPriorityAnalysisError(
                    "pending priority-analysis fields are inconsistent"
                )
            return

        if self.status is NewsPriorityStatus.ANALYZED:
            if self.priority_score is None:
                raise InvalidNewsPriorityAnalysisError(
                    "analyzed priority analysis must include priority_score"
                )

            if self.reason is None:
                raise InvalidNewsPriorityAnalysisError(
                    "analyzed priority analysis must include reason"
                )

            if self.failure_reason is not None:
                raise InvalidNewsPriorityAnalysisError(
                    "analyzed priority analysis must not include failure_reason"
                )

            return

        if self.priority_score is not None or self.reason is not None:
            raise InvalidNewsPriorityAnalysisError(
                "failed priority-analysis fields are inconsistent"
            )

        if self.failure_reason is None:
            raise InvalidNewsPriorityAnalysisError(
                "failed priority analysis must include failure_reason"
            )
