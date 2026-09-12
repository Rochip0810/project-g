from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_FAILURE_REASON_LENGTH = 2000
_MAX_PROVIDER_LENGTH = 64
_MAX_MODEL_LENGTH = 128
_MAX_VOICE_LENGTH = 128
_MAX_AUDIO_FORMAT_LENGTH = 16
_MAX_STORAGE_KEY_LENGTH = 1024
_SHA256_LENGTH = 64


class NewsNarrationAudioStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class InvalidNewsNarrationAudioError(ValueError):
    """Raised when narration-audio data is inconsistent."""


class InvalidNewsNarrationAudioTransitionError(RuntimeError):
    """Raised when a narration-audio transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsNarrationAudioError(f"{field_name} must be timezone-aware")


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
    max_length: int,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise InvalidNewsNarrationAudioError(f"{field_name} must not be empty")

    if len(normalized) > max_length:
        raise InvalidNewsNarrationAudioError(
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
        raise InvalidNewsNarrationAudioError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )

    if any(character not in "0123456789abcdef" for character in normalized):
        raise InvalidNewsNarrationAudioError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )

    return normalized


def _normalize_failure_reason(
    value: str,
) -> str:
    return _normalize_required_text(
        value,
        field_name="failure_reason",
        max_length=_MAX_FAILURE_REASON_LENGTH,
    )


@dataclass(frozen=True, slots=True)
class NewsNarrationAudioGeneration:
    audio_generation_id: UUID
    media_production_id: UUID
    audio_version: int
    status: NewsNarrationAudioStatus

    provider: str
    model: str
    voice: str
    audio_format: str
    source_text_sha256: str

    attempt_count: int
    storage_key: str | None
    byte_size: int | None
    content_sha256: str | None
    failure_reason: str | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        audio_generation_id: UUID,
        media_production_id: UUID,
        audio_version: int,
        provider: str,
        model: str,
        voice: str,
        audio_format: str,
        source_text_sha256: str,
        created_at: datetime,
    ) -> "NewsNarrationAudioGeneration":
        return cls(
            audio_generation_id=audio_generation_id,
            media_production_id=media_production_id,
            audio_version=audio_version,
            status=NewsNarrationAudioStatus.PENDING,
            provider=provider,
            model=model,
            voice=voice,
            audio_format=audio_format,
            source_text_sha256=source_text_sha256,
            attempt_count=0,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
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
    ) -> "NewsNarrationAudioGeneration":
        if self.status not in {
            NewsNarrationAudioStatus.PENDING,
            NewsNarrationAudioStatus.FAILED,
        }:
            raise InvalidNewsNarrationAudioTransitionError(
                "Narration audio can only start from pending or failed"
            )

        if started_at < self.updated_at:
            raise InvalidNewsNarrationAudioError("started_at must not be earlier than updated_at")

        return replace(
            self,
            status=NewsNarrationAudioStatus.GENERATING,
            attempt_count=self.attempt_count + 1,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
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
        completed_at: datetime,
    ) -> "NewsNarrationAudioGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsNarrationAudioStatus.GENERATED,
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            failure_reason=None,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        completed_at: datetime,
    ) -> "NewsNarrationAudioGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsNarrationAudioStatus.FAILED,
            storage_key=None,
            byte_size=None,
            content_sha256=None,
            failure_reason=_normalize_failure_reason(reason),
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def _require_generating(self) -> None:
        if self.status is not NewsNarrationAudioStatus.GENERATING:
            raise InvalidNewsNarrationAudioTransitionError("Narration audio must be generating")

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

        if self.audio_version < 1:
            raise InvalidNewsNarrationAudioError("audio_version must be at least 1")

        if self.attempt_count < 0:
            raise InvalidNewsNarrationAudioError("attempt_count must not be negative")

        object.__setattr__(
            self,
            "provider",
            _normalize_required_text(
                self.provider,
                field_name="provider",
                max_length=_MAX_PROVIDER_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "model",
            _normalize_required_text(
                self.model,
                field_name="model",
                max_length=_MAX_MODEL_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "voice",
            _normalize_required_text(
                self.voice,
                field_name="voice",
                max_length=_MAX_VOICE_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "audio_format",
            _normalize_required_text(
                self.audio_format,
                field_name="audio_format",
                max_length=_MAX_AUDIO_FORMAT_LENGTH,
            ).lower(),
        )
        object.__setattr__(
            self,
            "source_text_sha256",
            _normalize_sha256(
                self.source_text_sha256,
                field_name="source_text_sha256",
            ),
        )

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
            raise InvalidNewsNarrationAudioError("byte_size must be at least 1")

        if self.updated_at < self.created_at:
            raise InvalidNewsNarrationAudioError("updated_at must not be earlier than created_at")

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidNewsNarrationAudioError("started_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise InvalidNewsNarrationAudioError("completed_at must not be earlier than started_at")

        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is NewsNarrationAudioStatus.PENDING:
            self._validate_pending()
            return

        if self.attempt_count < 1:
            raise InvalidNewsNarrationAudioError(
                "started narration audio must have at least one attempt"
            )

        if self.started_at is None:
            raise InvalidNewsNarrationAudioError("started narration audio must include started_at")

        if self.status is NewsNarrationAudioStatus.GENERATING:
            self._validate_generating()
            return

        if self.completed_at is None:
            raise InvalidNewsNarrationAudioError(
                "finished narration audio must include completed_at"
            )

        if self.status is NewsNarrationAudioStatus.GENERATED:
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
            raise InvalidNewsNarrationAudioError("pending narration audio fields are inconsistent")

    def _validate_generating(self) -> None:
        if self.completed_at is not None or self.failure_reason is not None or self._has_artifact():
            raise InvalidNewsNarrationAudioError(
                "generating narration audio fields are inconsistent"
            )

    def _validate_generated(self) -> None:
        if self.failure_reason is not None:
            raise InvalidNewsNarrationAudioError(
                "generated narration audio must not include failure_reason"
            )

        if not self._has_complete_artifact():
            raise InvalidNewsNarrationAudioError(
                "generated narration audio must include complete artifact metadata"
            )

    def _validate_failed(self) -> None:
        if self.failure_reason is None:
            raise InvalidNewsNarrationAudioError(
                "failed narration audio must include failure_reason"
            )

        if self._has_artifact():
            raise InvalidNewsNarrationAudioError(
                "failed narration audio must not include artifact metadata"
            )

    def _has_artifact(self) -> bool:
        return (
            self.storage_key is not None
            or self.byte_size is not None
            or self.content_sha256 is not None
        )

    def _has_complete_artifact(self) -> bool:
        return (
            self.storage_key is not None
            and self.byte_size is not None
            and self.content_sha256 is not None
        )
