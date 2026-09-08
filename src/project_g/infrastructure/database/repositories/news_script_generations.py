from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from project_g.domain.news.script_generation import (
    InvalidNewsScriptGenerationError,
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.database.models import (
    NewsScriptGenerationRecord,
)
from project_g.ports.repositories.news_script_generations import (
    NewsScriptGenerationAlreadyExistsError,
    NewsScriptGenerationNotFoundError,
)


class SqlAlchemyNewsScriptGenerationRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        existing = self.get_by_intake_version(
            intake_id=generation.intake_id,
            generation_version=generation.generation_version,
        )

        if existing is not None:
            raise NewsScriptGenerationAlreadyExistsError(
                generation.intake_id,
                generation.generation_version,
            )

        record = NewsScriptGenerationRecord.from_domain(generation)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsScriptGenerationAlreadyExistsError(
                generation.intake_id,
                generation.generation_version,
            ) from error

        return record.to_domain()

    def update(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        record = self._session.get(
            NewsScriptGenerationRecord,
            generation.generation_id,
        )

        if (
            record is None
            or record.intake_id != generation.intake_id
            or record.generation_version != generation.generation_version
        ):
            raise NewsScriptGenerationNotFoundError(generation.generation_id)

        replacement = NewsScriptGenerationRecord.from_domain(generation)

        record.status = replacement.status
        record.ranking_score = replacement.ranking_score
        record.attempt_count = replacement.attempt_count
        record.failure_reason = replacement.failure_reason

        record.hook = replacement.hook
        record.main_narration = replacement.main_narration
        record.project_g_comment = replacement.project_g_comment
        record.closing = replacement.closing
        record.full_narration = replacement.full_narration
        record.evidence_snapshot = replacement.evidence_snapshot

        record.created_at = replacement.created_at
        record.started_at = replacement.started_at
        record.completed_at = replacement.completed_at
        record.updated_at = replacement.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_generation_id(
        self,
        generation_id: UUID,
    ) -> NewsScriptGeneration | None:
        record = self._session.get(
            NewsScriptGenerationRecord,
            generation_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None:
        statement = select(NewsScriptGenerationRecord).where(
            NewsScriptGenerationRecord.intake_id == intake_id,
            NewsScriptGenerationRecord.generation_version == generation_version,
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def claim_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsScriptGeneration | None:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise InvalidNewsScriptGenerationError("started_at must be timezone-aware")

        if stale_before is not None and (
            stale_before.tzinfo is None or stale_before.utcoffset() is None
        ):
            raise InvalidNewsScriptGenerationError("stale_before must be timezone-aware")

        claimable_status: ColumnElement[bool] = NewsScriptGenerationRecord.status.in_(
            (
                NewsScriptGenerationStatus.PENDING.value,
                NewsScriptGenerationStatus.FAILED.value,
            )
        )

        if stale_before is not None:
            claimable_status = or_(
                claimable_status,
                and_(
                    NewsScriptGenerationRecord.status
                    == NewsScriptGenerationStatus.GENERATING.value,
                    NewsScriptGenerationRecord.started_at.is_not(None),
                    NewsScriptGenerationRecord.started_at <= stale_before,
                ),
            )

        statement = (
            update(NewsScriptGenerationRecord)
            .where(
                NewsScriptGenerationRecord.intake_id == intake_id,
                NewsScriptGenerationRecord.generation_version == generation_version,
                claimable_status,
                NewsScriptGenerationRecord.updated_at <= started_at,
            )
            .values(
                status=(NewsScriptGenerationStatus.GENERATING.value),
                attempt_count=(NewsScriptGenerationRecord.attempt_count + 1),
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
            .returning(NewsScriptGenerationRecord)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        self._session.flush()

        return record.to_domain()
