from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole

_MAX_FAILURE_REASON_LENGTH = 2000


class NewsScriptGenerationStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class InvalidNewsScriptGenerationError(ValueError):
    """Raised when script-generation data is inconsistent."""


class InvalidNewsScriptGenerationTransitionError(RuntimeError):
    """Raised when a script-generation transition is not allowed."""


def _require_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidNewsScriptGenerationError(f"{field_name} must be timezone-aware")


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise InvalidNewsScriptGenerationError(f"{field_name} must not be empty")

    return normalized


def _normalize_failure_reason(
    value: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise InvalidNewsScriptGenerationError("failure_reason must not be empty")

    if len(normalized) > _MAX_FAILURE_REASON_LENGTH:
        raise InvalidNewsScriptGenerationError(
            f"failure_reason must not exceed {_MAX_FAILURE_REASON_LENGTH} characters"
        )

    return normalized


@dataclass(frozen=True, slots=True)
class NewsScriptEvidenceSnapshot:
    text: str
    source_id: str
    source_url: str
    competition_level: CompetitionLevel
    role: EvidenceRole

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "text",
            _normalize_required_text(
                self.text,
                field_name="evidence text",
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _normalize_required_text(
                self.source_id,
                field_name="evidence source_id",
            ),
        )
        object.__setattr__(
            self,
            "source_url",
            _normalize_required_text(
                self.source_url,
                field_name="evidence source_url",
            ),
        )


@dataclass(frozen=True, slots=True)
class NewsScriptGeneration:
    generation_id: UUID
    intake_id: UUID
    generation_version: int
    status: NewsScriptGenerationStatus
    ranking_score: int
    attempt_count: int
    failure_reason: str | None

    hook: str | None
    main_narration: str | None
    project_g_comment: str | None
    closing: str | None
    full_narration: str | None
    evidence_snapshot: tuple[NewsScriptEvidenceSnapshot, ...] | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def pending(
        cls,
        *,
        generation_id: UUID,
        intake_id: UUID,
        generation_version: int,
        ranking_score: int,
        created_at: datetime,
    ) -> "NewsScriptGeneration":
        return cls(
            generation_id=generation_id,
            intake_id=intake_id,
            generation_version=generation_version,
            status=NewsScriptGenerationStatus.PENDING,
            ranking_score=ranking_score,
            attempt_count=0,
            failure_reason=None,
            hook=None,
            main_narration=None,
            project_g_comment=None,
            closing=None,
            full_narration=None,
            evidence_snapshot=None,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            updated_at=created_at,
        )

    def start(
        self,
        *,
        started_at: datetime,
    ) -> "NewsScriptGeneration":
        if self.status not in {
            NewsScriptGenerationStatus.PENDING,
            NewsScriptGenerationStatus.FAILED,
        }:
            raise InvalidNewsScriptGenerationTransitionError(
                "Script generation can only start from pending or failed"
            )

        if started_at < self.updated_at:
            raise InvalidNewsScriptGenerationError("started_at must not be earlier than updated_at")

        return replace(
            self,
            status=NewsScriptGenerationStatus.GENERATING,
            attempt_count=self.attempt_count + 1,
            failure_reason=None,
            hook=None,
            main_narration=None,
            project_g_comment=None,
            closing=None,
            full_narration=None,
            evidence_snapshot=None,
            started_at=started_at,
            completed_at=None,
            updated_at=started_at,
        )

    def record_generated(
        self,
        *,
        hook: str,
        main_narration: str,
        project_g_comment: str,
        closing: str,
        full_narration: str,
        evidence_snapshot: tuple[NewsScriptEvidenceSnapshot, ...],
        completed_at: datetime,
    ) -> "NewsScriptGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsScriptGenerationStatus.GENERATED,
            failure_reason=None,
            hook=hook,
            main_narration=main_narration,
            project_g_comment=project_g_comment,
            closing=closing,
            full_narration=full_narration,
            evidence_snapshot=evidence_snapshot,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def mark_failed(
        self,
        *,
        reason: str,
        completed_at: datetime,
    ) -> "NewsScriptGeneration":
        self._require_generating()

        return replace(
            self,
            status=NewsScriptGenerationStatus.FAILED,
            failure_reason=_normalize_failure_reason(reason),
            hook=None,
            main_narration=None,
            project_g_comment=None,
            closing=None,
            full_narration=None,
            evidence_snapshot=None,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def _require_generating(self) -> None:
        if self.status is not NewsScriptGenerationStatus.GENERATING:
            raise InvalidNewsScriptGenerationTransitionError("Script generation must be generating")

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

        if self.generation_version < 1:
            raise InvalidNewsScriptGenerationError("generation_version must be at least 1")

        if not 0 <= self.ranking_score <= 100:
            raise InvalidNewsScriptGenerationError("ranking_score must be between 0 and 100")

        if self.attempt_count < 0:
            raise InvalidNewsScriptGenerationError("attempt_count must not be negative")

        if self.updated_at < self.created_at:
            raise InvalidNewsScriptGenerationError("updated_at must not be earlier than created_at")

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidNewsScriptGenerationError("started_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise InvalidNewsScriptGenerationError(
                "completed_at must not be earlier than started_at"
            )

        self._normalize_optional_fields()
        self._validate_status_fields()

    def _normalize_optional_fields(self) -> None:
        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _normalize_failure_reason(self.failure_reason),
            )

        for field_name in (
            "hook",
            "main_narration",
            "project_g_comment",
            "closing",
            "full_narration",
        ):
            value = getattr(self, field_name)

            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _normalize_required_text(
                        value,
                        field_name=field_name,
                    ),
                )

        if self.evidence_snapshot is not None:
            object.__setattr__(
                self,
                "evidence_snapshot",
                tuple(self.evidence_snapshot),
            )

    def _validate_status_fields(self) -> None:
        if self.status is NewsScriptGenerationStatus.PENDING:
            self._validate_pending()
            return

        if self.attempt_count < 1:
            raise InvalidNewsScriptGenerationError(
                "started generation must have at least one attempt"
            )

        if self.started_at is None:
            raise InvalidNewsScriptGenerationError("started generation must include started_at")

        if self.status is NewsScriptGenerationStatus.GENERATING:
            self._validate_generating()
            return

        if self.completed_at is None:
            raise InvalidNewsScriptGenerationError("finished generation must include completed_at")

        if self.status is NewsScriptGenerationStatus.GENERATED:
            self._validate_generated()
            return

        self._validate_failed()

    def _validate_pending(self) -> None:
        if (
            self.attempt_count != 0
            or self.failure_reason is not None
            or self.started_at is not None
            or self.completed_at is not None
            or self._has_script_output()
            or self.evidence_snapshot is not None
        ):
            raise InvalidNewsScriptGenerationError("pending generation fields are inconsistent")

    def _validate_generating(self) -> None:
        if (
            self.failure_reason is not None
            or self.completed_at is not None
            or self._has_script_output()
            or self.evidence_snapshot is not None
        ):
            raise InvalidNewsScriptGenerationError("generating generation fields are inconsistent")

    def _validate_generated(self) -> None:
        if self.failure_reason is not None:
            raise InvalidNewsScriptGenerationError(
                "generated generation must not include failure_reason"
            )

        if not self._has_complete_script_output():
            raise InvalidNewsScriptGenerationError(
                "generated generation must include complete script output"
            )

        if self.evidence_snapshot is None:
            raise InvalidNewsScriptGenerationError(
                "generated generation must include evidence_snapshot"
            )

    def _validate_failed(self) -> None:
        if self.failure_reason is None:
            raise InvalidNewsScriptGenerationError("failed generation must include failure_reason")

        if self._has_script_output() or self.evidence_snapshot is not None:
            raise InvalidNewsScriptGenerationError(
                "failed generation must not include script output"
            )

    def _has_script_output(self) -> bool:
        return any(
            value is not None
            for value in (
                self.hook,
                self.main_narration,
                self.project_g_comment,
                self.closing,
                self.full_narration,
            )
        )

    def _has_complete_script_output(self) -> bool:
        return all(
            value is not None
            for value in (
                self.hook,
                self.main_narration,
                self.project_g_comment,
                self.closing,
                self.full_narration,
            )
        )
