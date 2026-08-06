from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
    NewsMetadataStatus,
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


class NewsArticleMetadataRecord(Base):
    __tablename__ = "news_article_metadata"

    __table_args__ = (
        ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_article_metadata_intake_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "intake_id",
            name="uq_news_article_metadata_intake_id",
        ),
        CheckConstraint(
            ("status IN ('pending', 'extracted', 'manual', 'unavailable', 'failed')"),
            name="ck_news_article_metadata_status",
        ),
        Index(
            "ix_news_article_metadata_status_updated_at",
            "status",
            "updated_at",
            "metadata_id",
        ),
    )

    metadata_id: Mapped[UUID] = mapped_column(
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
    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
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
        metadata: NewsArticleMetadata,
    ) -> "NewsArticleMetadataRecord":
        return cls(
            metadata_id=metadata.metadata_id,
            intake_id=metadata.intake_id,
            status=metadata.status.value,
            title=metadata.title,
            published_at=metadata.published_at,
            description=metadata.description,
            failure_reason=metadata.failure_reason,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )

    def to_domain(self) -> NewsArticleMetadata:
        return NewsArticleMetadata(
            metadata_id=self.metadata_id,
            intake_id=self.intake_id,
            status=NewsMetadataStatus(self.status),
            title=self.title,
            published_at=_as_utc_optional(self.published_at),
            description=self.description,
            failure_reason=self.failure_reason,
            created_at=_as_utc(self.created_at),
            updated_at=_as_utc(self.updated_at),
        )
