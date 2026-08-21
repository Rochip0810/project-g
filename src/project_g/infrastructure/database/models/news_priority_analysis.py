from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)
from project_g.infrastructure.database.base import Base


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


class NewsPriorityAnalysisRecord(Base):
    __tablename__ = "news_priority_analyses"

    __table_args__ = (
        ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_priority_analyses_intake_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "intake_id",
            name="uq_news_priority_analyses_intake_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'analyzed', 'failed')",
            name="ck_news_priority_analyses_status",
        ),
        CheckConstraint(
            "priority_score IS NULL OR priority_score BETWEEN 0 AND 100",
            name="ck_news_priority_analyses_score",
        ),
        Index(
            "ix_news_priority_analyses_status_updated_at",
            "status",
            "updated_at",
            "analysis_id",
        ),
    )

    analysis_id: Mapped[UUID] = mapped_column(
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

    priority_score: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @classmethod
    def from_domain(
        cls,
        analysis: NewsPriorityAnalysis,
    ) -> "NewsPriorityAnalysisRecord":
        return cls(
            analysis_id=analysis.analysis_id,
            intake_id=analysis.intake_id,
            status=analysis.status.value,
            priority_score=analysis.priority_score,
            reason=analysis.reason,
            failure_reason=analysis.failure_reason,
            created_at=analysis.created_at,
            updated_at=analysis.updated_at,
        )

    def to_domain(self) -> NewsPriorityAnalysis:
        return NewsPriorityAnalysis(
            analysis_id=self.analysis_id,
            intake_id=self.intake_id,
            status=NewsPriorityStatus(self.status),
            priority_score=self.priority_score,
            reason=self.reason,
            failure_reason=self.failure_reason,
            created_at=_as_utc(self.created_at),
            updated_at=_as_utc(self.updated_at),
        )
