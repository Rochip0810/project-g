from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.infrastructure.database.models import (
    NewsProcessingJobRecord,
)
from project_g.ports.repositories.news_processing_jobs import (
    NewsProcessingJobAlreadyExistsError,
    NewsProcessingJobNotFoundError,
)


class SqlAlchemyNewsProcessingJobRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        if self.get_by_intake_id(job.intake_id) is not None:
            raise NewsProcessingJobAlreadyExistsError(job.intake_id)

        record = NewsProcessingJobRecord.from_domain(job)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsProcessingJobAlreadyExistsError(job.intake_id) from error

        return record.to_domain()

    def update(
        self,
        job: NewsProcessingJob,
    ) -> NewsProcessingJob:
        record = self._session.get(
            NewsProcessingJobRecord,
            job.job_id,
        )

        if record is None or record.intake_id != job.intake_id:
            raise NewsProcessingJobNotFoundError(job.job_id)

        record.status = job.status.value
        record.attempt_count = job.attempt_count
        record.last_error = job.last_error
        record.created_at = job.created_at
        record.started_at = job.started_at
        record.completed_at = job.completed_at
        record.updated_at = job.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_job_id(
        self,
        job_id: UUID,
    ) -> NewsProcessingJob | None:
        record = self._session.get(
            NewsProcessingJobRecord,
            job_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsProcessingJob | None:
        statement = select(NewsProcessingJobRecord).where(
            NewsProcessingJobRecord.intake_id == intake_id
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def get_oldest_pending(
        self,
    ) -> NewsProcessingJob | None:
        statement = (
            select(NewsProcessingJobRecord)
            .where(NewsProcessingJobRecord.status == NewsProcessingStatus.PENDING.value)
            .order_by(
                NewsProcessingJobRecord.created_at,
                NewsProcessingJobRecord.job_id,
            )
            .limit(1)
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()
