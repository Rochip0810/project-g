from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_FAILURE_REASON_LENGTH = 2000
_MAX_RENDERER_LENGTH = 64
_MAX_VIDEO_FORMAT_LENGTH = 16
_MAX_STORAGE_KEY_LENGTH = 1024
_SHA256_LENGTH = 64


class NewsVideoGenerationStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class InvalidNewsVideoGenerationError(ValueError):
    """Raised when video-generation data is inconsistent."""


class InvalidNewsVideoGenerationTransitionError(RuntimeError):
    """Raised when a video-generation transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsVideoGenerationError(f"{field_name} must be timezone-aware")


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
    max_length: int,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise InvalidNewsVideoGenerationError(f"{field_name} must not be empty")

    if len(normalized) > max_length:
        raise InvalidNewsVideoGenerationError(
            f"{field_name} must not exceed {max_length} characters"
        )

    return normalized


def _normalize_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    normalized = value.strip().lower()

    if len(normalized) != _SHA256_LENGTH:
        raise InvalidNewsVideoGenerationError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )

    if any(character not in "0123456789abcdef" for character in normalized):
        raise InvalidNewsVideoGenerationError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )

    return normalized


def _normalize_failure_reason(value: str) -> str:
    return _normalize_required_text(
        value,
        field_name="failure_reason",
        max_length=_MAX_FAILURE_REASON_LENGTH,
    )


@dataclass(frozen=True, slots=True)
class NewsVideoGeneration:
    video_generation_id: UUID
    media_production_id: UUID
    video_version: int
    status: NewsVideoGenerationStatus

    renderer: str
    video_format: str
    width: int
    height: int
    fps: int
    source_audio_generation_id: UUID
    source_audio_sha256: str

    attempt_count: int
    storage_key: str | None
    byte_size: int | None
    content_sha256: str | None
    duration_ms: int | None
    failure_reason: str | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        video_generation_id: UUID,
        media_production_id: UUID,
        video_version: int,
        renderer: str,
        video_format: str,
        width: int,
        height: int,
        fps: int,
        source_audio_generation_id: UUID,
        source_audio_sha256: str,
        created_at: datetime,
    ) -> "NewsVideoGeneration":
        return cls(
            video_generation_id=video_generation_id,
            media_production_id=media_production_id,
            video_version=video_version,
            status=NewsVideoGenerationStatus.PENDING,
            renderer=renderer,
            video_format=video_format,
            width=width,
            height=height,
            fps=fps,
            source_audio_generation_id=source_audio_generation_id,
            source_audio_sha256=source_audio_sha256,
            attempt_count=0,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
            duration_ms=None,
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
    ) -> "NewsVideoGeneration":
        if self.status not in {
            NewsVideoGenerationStatus.PENDING,
            NewsVideoGenerationStatus.FAILED,
        }:
            raise InvalidNewsVideoGenerationTransitionError(
                "Video generation can only start from pending or failed"
            )

        if started_at < self.updated_at:
            raise InvalidNewsVideoGenerationError("started_at must not be earlier than updated_at")

        return replace(
            self,
            status=NewsVideoGenerationStatus.GENERATING,
            attempt_count=self.attempt_count + 1,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
            duration_ms=None,
            failure_reason=None,
            started_at=started_at,
            completed_at=None,
            updated_at=started_at,
        )

    def record_generated(
        self,
        *,
        storage_key: str,
        byte_size: int,
        content_sha256: str,
        duration_ms: int,
        completed_at: datetime,
    ) -> "NewsVideoGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsVideoGenerationStatus.GENERATED,
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            duration_ms=duration_ms,
            failure_reason=None,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        completed_at: datetime,
    ) -> "NewsVideoGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsVideoGenerationStatus.FAILED,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
            duration_ms=None,
            failure_reason=_normalize_failure_reason(reason),
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def _require_generating(self) -> None:
        if self.status is not NewsVideoGenerationStatus.GENERATING:
            raise InvalidNewsVideoGenerationTransitionError("Video generation must be generating")

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

        if self.video_version < 1:
            raise InvalidNewsVideoGenerationError("video_version must be at least 1")

        if self.attempt_count < 0:
            raise InvalidNewsVideoGenerationError("attempt_count must not be negative")

        object.__setattr__(
            self,
            "renderer",
            _normalize_required_text(
                self.renderer,
                field_name="renderer",
                max_length=_MAX_RENDERER_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "video_format",
            _normalize_required_text(
                self.video_format,
                field_name="video_format",
                max_length=_MAX_VIDEO_FORMAT_LENGTH,
            ).lower(),
        )
        object.__setattr__(
            self,
            "source_audio_sha256",
            _normalize_sha256(
                self.source_audio_sha256,
                field_name="source_audio_sha256",
            ),
        )

        if self.width < 1:
            raise InvalidNewsVideoGenerationError("width must be at least 1")

        if self.height < 1:
            raise InvalidNewsVideoGenerationError("height must be at least 1")

        if self.fps < 1:
            raise InvalidNewsVideoGenerationError("fps must be at least 1")

        if self.storage_key is not None:
            object.__setattr__(
                self,
                "storage_key",
                _normalize_required_text(
                    self.storage_key,
                    field_name="storage_key",
                    max_length=_MAX_STORAGE_KEY_LENGTH,
                ),
            )

        if self.content_sha256 is not None:
            object.__setattr__(
                self,
                "content_sha256",
                _normalize_sha256(
                    self.content_sha256,
                    field_name="content_sha256",
                ),
            )

        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _normalize_failure_reason(self.failure_reason),
            )

        if self.byte_size is not None and self.byte_size < 1:
            raise InvalidNewsVideoGenerationError("byte_size must be at least 1")

        if self.duration_ms is not None and self.duration_ms < 1:
            raise InvalidNewsVideoGenerationError("duration_ms must be at least 1")

        if self.updated_at < self.created_at:
            raise InvalidNewsVideoGenerationError("updated_at must not be earlier than created_at")

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidNewsVideoGenerationError("started_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise InvalidNewsVideoGenerationError(
                "completed_at must not be earlier than started_at"
            )

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsVideoGenerationStatus.PENDING:
            self._validate_pending()
            return

        if self.attempt_count < 1:
            raise InvalidNewsVideoGenerationError(
                "started video generation must have at least one attempt"
            )

        if self.started_at is None:
            raise InvalidNewsVideoGenerationError(
                "started video generation must include started_at"
            )

        if self.status is NewsVideoGenerationStatus.GENERATING:
            self._validate_generating()
            return

        if self.completed_at is None:
            raise InvalidNewsVideoGenerationError(
                "finished video generation must include completed_at"
            )

        if self.status is NewsVideoGenerationStatus.GENERATED:
            self._validate_generated()
            return

        self._validate_failed()

    def _validate_pending(self) -> None:
        if (
            self.attempt_count != 0
            or self.started_at is not None
            or self.completed_at is not None
            or self.failure_reason is not None
            or self._has_artifact()
        ):
            raise InvalidNewsVideoGenerationError(
                "pending video generation fields are inconsistent"
            )

    def _validate_generating(self) -> None:
        if self.completed_at is not None or self.failure_reason is not None or self._has_artifact():
            raise InvalidNewsVideoGenerationError(
                "generating video generation fields are inconsistent"
            )

    def _validate_generated(self) -> None:
        if self.failure_reason is not None:
            raise InvalidNewsVideoGenerationError("generated video must not include failure_reason")

        if not self._has_complete_artifact():
            raise InvalidNewsVideoGenerationError(
                "generated video must include complete artifact metadata"
            )

    def _validate_failed(self) -> None:
        if self.failure_reason is None:
            raise InvalidNewsVideoGenerationError(
                "failed video generation must include failure_reason"
            )

        if self._has_artifact():
            raise InvalidNewsVideoGenerationError(
                "failed video generation must not include artifact metadata"
            )

    def _has_artifact(self) -> bool:
        return (
            self.storage_key is not None
            or self.byte_size is not None
            or self.content_sha256 is not None
            or self.duration_ms is not None
        )

    def _has_complete_artifact(self) -> bool:
        return (
            self.storage_key is not None
            and self.byte_size is not None
            and self.content_sha256 is not None
            and self.duration_ms is not None
        )
