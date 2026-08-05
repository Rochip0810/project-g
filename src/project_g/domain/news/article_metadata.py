from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_TITLE_LENGTH = 500
_MAX_DESCRIPTION_LENGTH = 2000
_MAX_FAILURE_REASON_LENGTH = 1000


class NewsMetadataStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    MANUAL = "manual"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class InvalidNewsArticleMetadataError(ValueError):
    """Raised when article metadata is inconsistent."""


class InvalidNewsMetadataTransitionError(RuntimeError):
    """Raised when a metadata transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsArticleMetadataError(f"{field_name} must be timezone-aware")


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
        raise InvalidNewsArticleMetadataError(
            f"{field_name} must not exceed {max_length} characters"
        )

    return normalized


@dataclass(frozen=True, slots=True)
class NewsArticleMetadata:
    metadata_id: UUID
    intake_id: UUID
    status: NewsMetadataStatus
    title: str | None
    published_at: datetime | None
    description: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        metadata_id: UUID,
        intake_id: UUID,
        created_at: datetime,
    ) -> "NewsArticleMetadata":
        return cls(
            metadata_id=metadata_id,
            intake_id=intake_id,
            status=NewsMetadataStatus.PENDING,
            title=None,
            published_at=None,
            description=None,
            failure_reason=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def record_extracted(
        self,
        *,
        title: str,
        published_at: datetime | None,
        description: str | None,
        updated_at: datetime,
    ) -> "NewsArticleMetadata":
        self._require_pending()

        return replace(
            self,
            status=NewsMetadataStatus.EXTRACTED,
            title=title,
            published_at=published_at,
            description=description,
            failure_reason=None,
            updated_at=updated_at,
        )

    def record_manual(
        self,
        *,
        title: str,
        published_at: datetime | None,
        description: str | None,
        updated_at: datetime,
    ) -> "NewsArticleMetadata":
        self._require_manual_entry_allowed()

        return replace(
            self,
            status=NewsMetadataStatus.MANUAL,
            title=title,
            published_at=published_at,
            description=description,
            failure_reason=None,
            updated_at=updated_at,
        )

    def mark_unavailable(
        self,
        *,
        reason: str,
        updated_at: datetime,
    ) -> "NewsArticleMetadata":
        self._require_pending()

        return replace(
            self,
            status=NewsMetadataStatus.UNAVAILABLE,
            title=None,
            published_at=None,
            description=None,
            failure_reason=reason,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        updated_at: datetime,
    ) -> "NewsArticleMetadata":
        self._require_pending()

        return replace(
            self,
            status=NewsMetadataStatus.FAILED,
            title=None,
            published_at=None,
            description=None,
            failure_reason=reason,
            updated_at=updated_at,
        )

    def _require_manual_entry_allowed(self) -> None:
        if self.status not in {
            NewsMetadataStatus.PENDING,
            NewsMetadataStatus.UNAVAILABLE,
        }:
            raise InvalidNewsMetadataTransitionError(
                "Manual metadata can only be recorded from pending or unavailable"
            )

    def _require_pending(self) -> None:
        if self.status is not NewsMetadataStatus.PENDING:
            raise InvalidNewsMetadataTransitionError("Metadata can only transition from pending")

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
            raise InvalidNewsArticleMetadataError("updated_at must not be earlier than created_at")

        if self.published_at is not None:
            _require_aware(
                self.published_at,
                field_name="published_at",
            )

        normalized_title = _normalize_optional_text(
            self.title,
            field_name="title",
            max_length=_MAX_TITLE_LENGTH,
        )
        normalized_description = _normalize_optional_text(
            self.description,
            field_name="description",
            max_length=_MAX_DESCRIPTION_LENGTH,
        )
        normalized_failure_reason = _normalize_optional_text(
            self.failure_reason,
            field_name="failure_reason",
            max_length=_MAX_FAILURE_REASON_LENGTH,
        )

        object.__setattr__(
            self,
            "title",
            normalized_title,
        )
        object.__setattr__(
            self,
            "description",
            normalized_description,
        )
        object.__setattr__(
            self,
            "failure_reason",
            normalized_failure_reason,
        )

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsMetadataStatus.PENDING:
            if (
                self.title is not None
                or self.published_at is not None
                or self.description is not None
                or self.failure_reason is not None
            ):
                raise InvalidNewsArticleMetadataError("pending metadata fields are inconsistent")
            return

        if self.status in {
            NewsMetadataStatus.EXTRACTED,
            NewsMetadataStatus.MANUAL,
        }:
            if self.title is None:
                raise InvalidNewsArticleMetadataError("completed metadata must include a title")

            if self.failure_reason is not None:
                raise InvalidNewsArticleMetadataError(
                    "completed metadata must not include a failure reason"
                )
            return

        if self.title is not None or self.published_at is not None or self.description is not None:
            raise InvalidNewsArticleMetadataError(
                "unavailable or failed metadata must not include article data"
            )

        if self.failure_reason is None:
            raise InvalidNewsArticleMetadataError(
                "unavailable or failed metadata must include a reason"
            )
