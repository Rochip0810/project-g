from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from project_g.domain.news.video_generation import (
    InvalidNewsVideoGenerationError,
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.infrastructure.database.models.news_video_generation import (
    NewsVideoGenerationRecord,
)
from project_g.ports.repositories.news_video_generations import (
    NewsVideoGenerationAlreadyExistsError,
    NewsVideoGenerationNotFoundError,
)


class SqlAlchemyNewsVideoGenerationRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        existing = self.get_by_media_production_version(
            media_production_id=generation.media_production_id,
            video_version=generation.video_version,
        )

        if existing is not None:
            raise NewsVideoGenerationAlreadyExistsError(
                generation.media_production_id,
                generation.video_version,
            )

        record = NewsVideoGenerationRecord.from_domain(generation)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsVideoGenerationAlreadyExistsError(
                generation.media_production_id,
                generation.video_version,
            ) from error

        return record.to_domain()

    def update(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        record = self._session.get(
            NewsVideoGenerationRecord,
            generation.video_generation_id,
        )

        if (
            record is None
            or record.media_production_id != generation.media_production_id
            or record.video_version != generation.video_version
        ):
            raise NewsVideoGenerationNotFoundError(generation.video_generation_id)

        replacement = NewsVideoGenerationRecord.from_domain(generation)

        record.status = replacement.status
        record.renderer = replacement.renderer
        record.video_format = replacement.video_format
        record.width = replacement.width
        record.height = replacement.height
        record.fps = replacement.fps
        record.source_audio_generation_id = replacement.source_audio_generation_id
        record.source_audio_sha256 = replacement.source_audio_sha256

        record.attempt_count = replacement.attempt_count
        record.storage_key = replacement.storage_key
        record.byte_size = replacement.byte_size
        record.content_sha256 = replacement.content_sha256
        record.duration_ms = replacement.duration_ms
        record.failure_reason = replacement.failure_reason

        record.created_at = replacement.created_at
        record.started_at = replacement.started_at
        record.completed_at = replacement.completed_at
        record.updated_at = replacement.updated_at

        self._session.flush()

        return record.to_domain()

    def record_generated_if_current(
        self,
        *,
        video_generation_id: UUID,
        expected_attempt_number: int,
        storage_key: str,
        byte_size: int,
        content_sha256: str,
        duration_ms: int,
        completed_at: datetime,
    ) -> NewsVideoGeneration | None:
        if expected_attempt_number < 1:
            raise InvalidNewsVideoGenerationError("expected_attempt_number must be at least 1")

        current = self.get_by_video_generation_id(video_generation_id)

        if current is None:
            return None

        if (
            current.status is not NewsVideoGenerationStatus.GENERATING
            or current.attempt_count != expected_attempt_number
        ):
            return None

        # Validate output metadata and the completion timestamp
        # using the existing domain transition.
        generated = current.record_generated(
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            duration_ms=duration_ms,
            completed_at=completed_at,
        )

        # The SQL predicate is the authoritative ownership check.
        # Another worker may have reclaimed this generation after
        # the domain object above was read.
        statement = (
            update(NewsVideoGenerationRecord)
            .where(
                NewsVideoGenerationRecord.video_generation_id == video_generation_id,
                NewsVideoGenerationRecord.status == NewsVideoGenerationStatus.GENERATING.value,
                NewsVideoGenerationRecord.attempt_count == expected_attempt_number,
            )
            .values(
                status=NewsVideoGenerationStatus.GENERATED.value,
                storage_key=generated.storage_key,
                byte_size=generated.byte_size,
                content_sha256=generated.content_sha256,
                duration_ms=generated.duration_ms,
                failure_reason=None,
                completed_at=generated.completed_at,
                updated_at=generated.updated_at,
            )
            .returning(NewsVideoGenerationRecord)
            .execution_options(populate_existing=True)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        self._session.flush()

        return record.to_domain()

    def mark_failed_if_current(
        self,
        *,
        video_generation_id: UUID,
        expected_attempt_number: int,
        reason: str,
        completed_at: datetime,
    ) -> NewsVideoGeneration | None:
        if expected_attempt_number < 1:
            raise InvalidNewsVideoGenerationError("expected_attempt_number must be at least 1")

        current = self.get_by_video_generation_id(video_generation_id)

        if current is None:
            return None

        if (
            current.status is not NewsVideoGenerationStatus.GENERATING
            or current.attempt_count != expected_attempt_number
        ):
            return None

        # Validate the failure reason and completion timestamp
        # using the existing domain transition.
        failed = current.mark_failed(
            reason=reason,
            completed_at=completed_at,
        )

        # Only the worker that still owns this attempt
        # may persist the failure.
        statement = (
            update(NewsVideoGenerationRecord)
            .where(
                NewsVideoGenerationRecord.video_generation_id == video_generation_id,
                NewsVideoGenerationRecord.status == NewsVideoGenerationStatus.GENERATING.value,
                NewsVideoGenerationRecord.attempt_count == expected_attempt_number,
            )
            .values(
                status=NewsVideoGenerationStatus.FAILED.value,
                storage_key=None,
                byte_size=None,
                content_sha256=None,
                duration_ms=None,
                failure_reason=failed.failure_reason,
                completed_at=failed.completed_at,
                updated_at=failed.updated_at,
            )
            .returning(NewsVideoGenerationRecord)
            .execution_options(populate_existing=True)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        self._session.flush()

        return record.to_domain()

    def get_by_video_generation_id(
        self,
        video_generation_id: UUID,
    ) -> NewsVideoGeneration | None:
        record = self._session.get(
            NewsVideoGenerationRecord,
            video_generation_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
    ) -> NewsVideoGeneration | None:
        statement = select(NewsVideoGenerationRecord).where(
            NewsVideoGenerationRecord.media_production_id == media_production_id,
            NewsVideoGenerationRecord.video_version == video_version,
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
        expected_attempt_number: int | None = None,
    ) -> NewsVideoGeneration | None:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise InvalidNewsVideoGenerationError("started_at must be timezone-aware")

        if stale_before is not None and (
            stale_before.tzinfo is None or stale_before.utcoffset() is None
        ):
            raise InvalidNewsVideoGenerationError("stale_before must be timezone-aware")

        if expected_attempt_number is not None and expected_attempt_number < 1:
            raise InvalidNewsVideoGenerationError("expected_attempt_number must be at least 1")

        claimable_status: ColumnElement[bool] = NewsVideoGenerationRecord.status.in_(
            (
                NewsVideoGenerationStatus.PENDING.value,
                NewsVideoGenerationStatus.FAILED.value,
            )
        )

        if stale_before is not None:
            claimable_status = or_(
                claimable_status,
                and_(
                    NewsVideoGenerationRecord.status == NewsVideoGenerationStatus.GENERATING.value,
                    NewsVideoGenerationRecord.started_at.is_not(None),
                    NewsVideoGenerationRecord.started_at <= stale_before,
                ),
            )

        if expected_attempt_number is not None:
            claimable_status = and_(
                claimable_status,
                NewsVideoGenerationRecord.attempt_count == expected_attempt_number - 1,
            )

        statement = (
            update(NewsVideoGenerationRecord)
            .where(
                NewsVideoGenerationRecord.media_production_id == media_production_id,
                NewsVideoGenerationRecord.video_version == video_version,
                claimable_status,
                NewsVideoGenerationRecord.updated_at <= started_at,
            )
            .values(
                status=NewsVideoGenerationStatus.GENERATING.value,
                attempt_count=(NewsVideoGenerationRecord.attempt_count + 1),
                storage_key=None,
                byte_size=None,
                content_sha256=None,
                duration_ms=None,
                failure_reason=None,
                started_at=started_at,
                completed_at=None,
                updated_at=started_at,
            )
            .returning(NewsVideoGenerationRecord)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        self._session.flush()

        return record.to_domain()
