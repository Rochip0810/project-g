from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.infrastructure.database.base import Base


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


class ManualNewsIntakeRecord(Base):
    __tablename__ = "manual_news_intakes"

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id"],
            ["news_sources.source_id"],
            name="fk_manual_news_intakes_source_id",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "canonical_url",
            name="uq_manual_news_intakes_canonical_url",
        ),
        Index(
            "ix_manual_news_intakes_source_submitted_at",
            "source_id",
            "submitted_at",
        ),
    )

    intake_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    submitted_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    canonical_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @classmethod
    def from_domain(
        cls,
        intake: ManualNewsIntake,
    ) -> "ManualNewsIntakeRecord":
        return cls(
            intake_id=intake.intake_id,
            source_id=intake.source_id,
            submitted_url=intake.submitted_url,
            canonical_url=intake.canonical_url,
            submitted_at=intake.submitted_at,
        )

    def to_domain(self) -> ManualNewsIntake:
        return ManualNewsIntake(
            intake_id=self.intake_id,
            source_id=self.source_id,
            submitted_url=self.submitted_url,
            canonical_url=self.canonical_url,
            submitted_at=_as_utc(self.submitted_at),
        )
