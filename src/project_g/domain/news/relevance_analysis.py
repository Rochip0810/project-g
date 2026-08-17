from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_REASON_LENGTH = 2000
_MAX_FAILURE_REASON_LENGTH = 1000


class NewsRelevanceStatus(StrEnum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    FAILED = "failed"


class NewsRelevanceDecision(StrEnum):
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


class InvalidNewsRelevanceAnalysisError(ValueError):
    """Raised when relevance-analysis data is inconsistent."""


class InvalidNewsRelevanceTransitionError(RuntimeError):
    """Raised when a relevance-analysis transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsRelevanceAnalysisError(f"{field_name} must be timezone-aware")


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
        raise InvalidNewsRelevanceAnalysisError(
            f"{field_name} must not exceed {max_length} characters"
        )

    return normalized


@dataclass(frozen=True, slots=True)
class NewsRelevanceAnalysis:
    analysis_id: UUID
    intake_id: UUID
    status: NewsRelevanceStatus
    relevance_score: int | None
    decision: NewsRelevanceDecision | None
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
    ) -> "NewsRelevanceAnalysis":
        return cls(
            analysis_id=analysis_id,
            intake_id=intake_id,
            status=NewsRelevanceStatus.PENDING,
            relevance_score=None,
            decision=None,
            reason=None,
            failure_reason=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def record_analyzed(
        self,
        *,
        relevance_score: int,
        decision: NewsRelevanceDecision,
        reason: str,
        updated_at: datetime,
    ) -> "NewsRelevanceAnalysis":
        self._require_pending()

        return replace(
            self,
            status=NewsRelevanceStatus.ANALYZED,
            relevance_score=relevance_score,
            decision=decision,
            reason=reason,
            failure_reason=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        updated_at: datetime,
    ) -> "NewsRelevanceAnalysis":
        self._require_pending()

        return replace(
            self,
            status=NewsRelevanceStatus.FAILED,
            relevance_score=None,
            decision=None,
            reason=None,
            failure_reason=reason,
            updated_at=updated_at,
        )

    def _require_pending(self) -> None:
        if self.status is not NewsRelevanceStatus.PENDING:
            raise InvalidNewsRelevanceTransitionError(
                "Relevance analysis can only transition from pending"
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
            raise InvalidNewsRelevanceAnalysisError(
                "updated_at must not be earlier than created_at"
            )

        if self.relevance_score is not None and not 0 <= self.relevance_score <= 100:
            raise InvalidNewsRelevanceAnalysisError("relevance_score must be between 0 and 100")

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
        if self.status is NewsRelevanceStatus.PENDING:
            if (
                self.relevance_score is not None
                or self.decision is not None
                or self.reason is not None
                or self.failure_reason is not None
            ):
                raise InvalidNewsRelevanceAnalysisError(
                    "pending relevance-analysis fields are inconsistent"
                )
            return

        if self.status is NewsRelevanceStatus.ANALYZED:
            if self.relevance_score is None:
                raise InvalidNewsRelevanceAnalysisError(
                    "analyzed relevance analysis must include relevance_score"
                )

            if self.decision is None:
                raise InvalidNewsRelevanceAnalysisError(
                    "analyzed relevance analysis must include decision"
                )

            if self.reason is None:
                raise InvalidNewsRelevanceAnalysisError(
                    "analyzed relevance analysis must include reason"
                )

            if self.failure_reason is not None:
                raise InvalidNewsRelevanceAnalysisError(
                    "analyzed relevance analysis must not include failure_reason"
                )

            return

        if self.relevance_score is not None or self.decision is not None or self.reason is not None:
            raise InvalidNewsRelevanceAnalysisError(
                "failed relevance-analysis fields are inconsistent"
            )

        if self.failure_reason is None:
            raise InvalidNewsRelevanceAnalysisError(
                "failed relevance analysis must include failure_reason"
            )
