from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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

from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
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


class NewsVideoGenerationRecord(Base):
    __tablename__ = "news_video_generations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["media_production_id"],
            ["news_media_productions.media_production_id"],
            name="fk_news_video_generations_media_production_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "media_production_id",
            "video_version",
            name="uq_news_video_generations_media_version",
        ),
        CheckConstraint(
            "status IN ('pending', 'generating', 'generated', 'failed')",
            name="ck_news_video_generations_status",
        ),
        CheckConstraint(
            "video_version >= 1",
            name="ck_news_video_generations_version",
        ),
        CheckConstraint(
            "width >= 1",
            name="ck_news_video_generations_width",
        ),
        CheckConstraint(
            "height >= 1",
            name="ck_news_video_generations_height",
        ),
        CheckConstraint(
            "fps >= 1",
            name="ck_news_video_generations_fps",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_video_generations_attempt_count",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 1",
            name="ck_news_video_generations_byte_size",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 1",
            name="ck_news_video_generations_duration_ms",
        ),
        Index(
            "ix_news_video_generations_status_updated_at",
            "status",
            "updated_at",
            "video_generation_id",
        ),
    )

    video_generation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    media_production_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    video_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    renderer: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    video_format: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    fps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    source_audio_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    byte_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    content_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        BigInteger,
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
        generation: NewsVideoGeneration,
    ) -> "NewsVideoGenerationRecord":
        return cls(
            video_generation_id=generation.video_generation_id,
            media_production_id=generation.media_production_id,
            video_version=generation.video_version,
            status=generation.status.value,
            renderer=generation.renderer,
            video_format=generation.video_format,
            width=generation.width,
            height=generation.height,
            fps=generation.fps,
            source_audio_sha256=generation.source_audio_sha256,
            attempt_count=generation.attempt_count,
            storage_key=generation.storage_key,
            byte_size=generation.byte_size,
            content_sha256=generation.content_sha256,
            duration_ms=generation.duration_ms,
            failure_reason=generation.failure_reason,
            created_at=generation.created_at,
            started_at=generation.started_at,
            completed_at=generation.completed_at,
            updated_at=generation.updated_at,
        )

    def to_domain(self) -> NewsVideoGeneration:
        return NewsVideoGeneration(
            video_generation_id=self.video_generation_id,
            media_production_id=self.media_production_id,
            video_version=self.video_version,
            status=NewsVideoGenerationStatus(self.status),
            renderer=self.renderer,
            video_format=self.video_format,
            width=self.width,
            height=self.height,
            fps=self.fps,
            source_audio_sha256=self.source_audio_sha256,
            attempt_count=self.attempt_count,
            storage_key=self.storage_key,
            byte_size=self.byte_size,
            content_sha256=self.content_sha256,
            duration_ms=self.duration_ms,
            failure_reason=self.failure_reason,
            created_at=_as_utc(self.created_at),
            started_at=_as_utc_optional(self.started_at),
            completed_at=_as_utc_optional(self.completed_at),
            updated_at=_as_utc(self.updated_at),
        )
