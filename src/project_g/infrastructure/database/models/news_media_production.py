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

from project_g.domain.news.media_production import (
    NewsMediaProduction,
    NewsMediaProductionStatus,
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


class NewsMediaProductionRecord(Base):
    __tablename__ = "news_media_productions"

    __table_args__ = (
        ForeignKeyConstraint(
            ["script_generation_id"],
            ["news_script_generations.generation_id"],
            name="fk_news_media_productions_script_generation_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "script_generation_id",
            "media_version",
            name="uq_news_media_productions_script_version",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_news_media_productions_status",
        ),
        CheckConstraint(
            "media_version >= 1",
            name="ck_news_media_productions_version",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_media_productions_attempt_count",
        ),
        Index(
            "ix_news_media_productions_status_updated_at",
            "status",
            "updated_at",
            "media_production_id",
        ),
    )

    media_production_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    script_generation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    media_version: Mapped[int] = mapped_column(
        Integer,
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
    failure_reason: Mapped[str | None] = mapped_column(
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
        production: NewsMediaProduction,
    ) -> "NewsMediaProductionRecord":
        return cls(
            media_production_id=production.media_production_id,
            script_generation_id=production.script_generation_id,
            media_version=production.media_version,
            status=production.status.value,
            attempt_count=production.attempt_count,
            failure_reason=production.failure_reason,
            created_at=production.created_at,
            started_at=production.started_at,
            completed_at=production.completed_at,
            updated_at=production.updated_at,
        )

    def to_domain(self) -> NewsMediaProduction:
        return NewsMediaProduction(
            media_production_id=self.media_production_id,
            script_generation_id=self.script_generation_id,
            media_version=self.media_version,
            status=NewsMediaProductionStatus(self.status),
            attempt_count=self.attempt_count,
            failure_reason=self.failure_reason,
            created_at=_as_utc(self.created_at),
            started_at=_as_utc_optional(self.started_at),
            completed_at=_as_utc_optional(self.completed_at),
            updated_at=_as_utc(self.updated_at),
        )
