from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.infrastructure.database.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsSourceRecord(Base):
    __tablename__ = "news_sources"

    __table_args__ = (
        CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_news_sources_priority",
        ),
        CheckConstraint(
            "source_type IN ('website', 'rss', 'api')",
            name="ck_news_sources_source_type",
        ),
        CheckConstraint(
            "status IN ('enabled', 'paused', 'disabled')",
            name="ck_news_sources_status",
        ),
        Index(
            "ix_news_sources_collectable_order",
            "status",
            "is_official",
            "priority",
            "name",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    base_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_official: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    @classmethod
    def from_domain(
        cls,
        source: NewsSource,
    ) -> "NewsSourceRecord":
        return cls(
            source_id=source.source_id,
            name=source.name,
            source_type=source.source_type.value,
            base_url=source.base_url,
            is_official=source.is_official,
            status=source.status.value,
            priority=source.priority,
        )

    def apply_domain(self, source: NewsSource) -> None:
        self.name = source.name
        self.source_type = source.source_type.value
        self.base_url = source.base_url
        self.is_official = source.is_official
        self.status = source.status.value
        self.priority = source.priority
        self.updated_at = _utc_now()

    def to_domain(self) -> NewsSource:
        return NewsSource(
            source_id=self.source_id,
            name=self.name,
            source_type=SourceType(self.source_type),
            base_url=self.base_url,
            is_official=self.is_official,
            status=SourceStatus(self.status),
            priority=self.priority,
        )
