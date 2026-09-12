from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from project_g.domain.news.narration_audio import (
    InvalidNewsNarrationAudioError,
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.infrastructure.database.models import (
    NewsNarrationAudioGenerationRecord,
)
from project_g.ports.repositories.news_narration_audio_generations import (
    NewsNarrationAudioAlreadyExistsError,
    NewsNarrationAudioNotFoundError,
)


class SqlAlchemyNewsNarrationAudioGenerationRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        existing = self.get_by_media_production_version(
            media_production_id=generation.media_production_id,
            audio_version=generation.audio_version,
        )

        if existing is not None:
            raise NewsNarrationAudioAlreadyExistsError(
                generation.media_production_id,
                generation.audio_version,
            )

        record = NewsNarrationAudioGenerationRecord.from_domain(generation)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsNarrationAudioAlreadyExistsError(
                generation.media_production_id,
                generation.audio_version,
            ) from error

        return record.to_domain()

    def update(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        record = self._session.get(
            NewsNarrationAudioGenerationRecord,
            generation.audio_generation_id,
        )

        if (
            record is None
            or record.media_production_id != generation.media_production_id
            or record.audio_version != generation.audio_version
        ):
            raise NewsNarrationAudioNotFoundError(generation.audio_generation_id)

        replacement = NewsNarrationAudioGenerationRecord.from_domain(generation)

        record.status = replacement.status
        record.provider = replacement.provider
        record.model = replacement.model
        record.voice = replacement.voice
        record.audio_format = replacement.audio_format
        record.source_text_sha256 = replacement.source_text_sha256

        record.attempt_count = replacement.attempt_count
        record.storage_key = replacement.storage_key
        record.byte_size = replacement.byte_size
        record.content_sha256 = replacement.content_sha256
        record.failure_reason = replacement.failure_reason

        record.created_at = replacement.created_at
        record.started_at = replacement.started_at
        record.completed_at = replacement.completed_at
        record.updated_at = replacement.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_audio_generation_id(
        self,
        audio_generation_id: UUID,
    ) -> NewsNarrationAudioGeneration | None:
        record = self._session.get(
            NewsNarrationAudioGenerationRecord,
            audio_generation_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
    ) -> NewsNarrationAudioGeneration | None:
        statement = select(NewsNarrationAudioGenerationRecord).where(
            NewsNarrationAudioGenerationRecord.media_production_id == media_production_id,
            NewsNarrationAudioGenerationRecord.audio_version == audio_version,
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsNarrationAudioGeneration | None:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise InvalidNewsNarrationAudioError("started_at must be timezone-aware")

        if stale_before is not None and (
            stale_before.tzinfo is None or stale_before.utcoffset() is None
        ):
            raise InvalidNewsNarrationAudioError("stale_before must be timezone-aware")

        claimable_status: ColumnElement[bool] = NewsNarrationAudioGenerationRecord.status.in_(
            (
                NewsNarrationAudioStatus.PENDING.value,
                NewsNarrationAudioStatus.FAILED.value,
            )
        )

        if stale_before is not None:
            claimable_status = or_(
                claimable_status,
                and_(
                    NewsNarrationAudioGenerationRecord.status
                    == NewsNarrationAudioStatus.GENERATING.value,
                    NewsNarrationAudioGenerationRecord.started_at.is_not(None),
                    NewsNarrationAudioGenerationRecord.started_at <= stale_before,
                ),
            )

        statement = (
            update(NewsNarrationAudioGenerationRecord)
            .where(
                NewsNarrationAudioGenerationRecord.media_production_id == media_production_id,
                NewsNarrationAudioGenerationRecord.audio_version == audio_version,
                claimable_status,
                NewsNarrationAudioGenerationRecord.updated_at <= started_at,
            )
            .values(
                status=NewsNarrationAudioStatus.GENERATING.value,
                attempt_count=(NewsNarrationAudioGenerationRecord.attempt_count + 1),
                storage_key=None,
                byte_size=None,
                content_sha256=None,
                failure_reason=None,
                started_at=started_at,
                completed_at=None,
                updated_at=started_at,
            )
            .returning(NewsNarrationAudioGenerationRecord)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        self._session.flush()

        return record.to_domain()
