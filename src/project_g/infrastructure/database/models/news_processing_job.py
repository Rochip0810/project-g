from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.infrastructure.database.base import Base


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _as_utc_optional(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    return _as_utc(value)


class NewsProcessingJobRecord(Base):
    __tablename__ = "news_processing_jobs"

    __table_args__ = (
        ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_processing_jobs_intake_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "intake_id",
            name="uq_news_processing_jobs_intake_id",
        ),
        CheckConstraint(
            ("status IN ('pending', 'processing', 'completed', 'failed')"),
            name="ck_news_processing_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_processing_jobs_attempt_count",
        ),
        Index(
            "ix_news_processing_jobs_status_created_at",
            "status",
            "created_at",
            "job_id",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    intake_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @classmethod
    def from_domain(
        cls,
        job: NewsProcessingJob,
    ) -> "NewsProcessingJobRecord":
        return cls(
            job_id=job.job_id,
            intake_id=job.intake_id,
            status=job.status.value,
            attempt_count=job.attempt_count,
            last_error=job.last_error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )

    def to_domain(self) -> NewsProcessingJob:
        return NewsProcessingJob(
            job_id=self.job_id,
            intake_id=self.intake_id,
            status=NewsProcessingStatus(self.status),
            attempt_count=self.attempt_count,
            last_error=self.last_error,
            created_at=_as_utc(self.created_at),
            started_at=_as_utc_optional(self.started_at),
            completed_at=_as_utc_optional(self.completed_at),
            updated_at=_as_utc(self.updated_at),
        )
