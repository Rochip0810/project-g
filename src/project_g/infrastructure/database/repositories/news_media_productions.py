from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.infrastructure.database.models import (
    NewsMediaProductionRecord,
)
from project_g.ports.repositories.news_media_productions import (
    NewsMediaProductionAlreadyExistsError,
    NewsMediaProductionNotFoundError,
)


class SqlAlchemyNewsMediaProductionRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        existing = self.get_by_script_generation_version(
            script_generation_id=production.script_generation_id,
            media_version=production.media_version,
        )

        if existing is not None:
            raise NewsMediaProductionAlreadyExistsError(
                production.script_generation_id,
                production.media_version,
            )

        record = NewsMediaProductionRecord.from_domain(production)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsMediaProductionAlreadyExistsError(
                production.script_generation_id,
                production.media_version,
            ) from error

        return record.to_domain()

    def update(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        record = self._session.get(
            NewsMediaProductionRecord,
            production.media_production_id,
        )

        if (
            record is None
            or record.script_generation_id != production.script_generation_id
            or record.media_version != production.media_version
        ):
            raise NewsMediaProductionNotFoundError(production.media_production_id)

        replacement = NewsMediaProductionRecord.from_domain(production)

        record.status = replacement.status
        record.attempt_count = replacement.attempt_count
        record.failure_reason = replacement.failure_reason

        record.created_at = replacement.created_at
        record.started_at = replacement.started_at
        record.completed_at = replacement.completed_at
        record.updated_at = replacement.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_media_production_id(
        self,
        media_production_id: UUID,
    ) -> NewsMediaProduction | None:
        record = self._session.get(
            NewsMediaProductionRecord,
            media_production_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_script_generation_version(
        self,
        *,
        script_generation_id: UUID,
        media_version: int,
    ) -> NewsMediaProduction | None:
        statement = select(NewsMediaProductionRecord).where(
            NewsMediaProductionRecord.script_generation_id == script_generation_id,
            NewsMediaProductionRecord.media_version == media_version,
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()
