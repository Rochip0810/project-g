from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
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


class NewsScriptGenerationRecord(Base):
    __tablename__ = "news_script_generations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_script_generations_intake_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "intake_id",
            "generation_version",
            name="uq_news_script_generations_intake_version",
        ),
        CheckConstraint(
            "status IN ('pending', 'generating', 'generated', 'failed')",
            name="ck_news_script_generations_status",
        ),
        CheckConstraint(
            "generation_version >= 1",
            name="ck_news_script_generations_version",
        ),
        CheckConstraint(
            "ranking_score BETWEEN 0 AND 100",
            name="ck_news_script_generations_ranking_score",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_script_generations_attempt_count",
        ),
        Index(
            "ix_news_script_generations_status_updated_at",
            "status",
            "updated_at",
            "generation_id",
        ),
    )

    generation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    intake_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    generation_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    ranking_score: Mapped[int] = mapped_column(
        SmallInteger,
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

    hook: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    main_narration: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    project_g_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    closing: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    full_narration: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    evidence_snapshot: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON,
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
        generation: NewsScriptGeneration,
    ) -> "NewsScriptGenerationRecord":
        evidence = None

        if generation.evidence_snapshot is not None:
            evidence = [
                {
                    "text": item.text,
                    "source_id": item.source_id,
                    "source_url": item.source_url,
                    "competition_level": item.competition_level.value,
                    "role": item.role.value,
                }
                for item in generation.evidence_snapshot
            ]

        return cls(
            generation_id=generation.generation_id,
            intake_id=generation.intake_id,
            generation_version=generation.generation_version,
            status=generation.status.value,
            ranking_score=generation.ranking_score,
            attempt_count=generation.attempt_count,
            failure_reason=generation.failure_reason,
            hook=generation.hook,
            main_narration=generation.main_narration,
            project_g_comment=generation.project_g_comment,
            closing=generation.closing,
            full_narration=generation.full_narration,
            evidence_snapshot=evidence,
            created_at=generation.created_at,
            started_at=generation.started_at,
            completed_at=generation.completed_at,
            updated_at=generation.updated_at,
        )

    def to_domain(self) -> NewsScriptGeneration:
        evidence = None

        if self.evidence_snapshot is not None:
            evidence = tuple(
                NewsScriptEvidenceSnapshot(
                    text=item["text"],
                    source_id=item["source_id"],
                    source_url=item["source_url"],
                    competition_level=CompetitionLevel(item["competition_level"]),
                    role=EvidenceRole(item["role"]),
                )
                for item in self.evidence_snapshot
            )

        return NewsScriptGeneration(
            generation_id=self.generation_id,
            intake_id=self.intake_id,
            generation_version=self.generation_version,
            status=NewsScriptGenerationStatus(self.status),
            ranking_score=self.ranking_score,
            attempt_count=self.attempt_count,
            failure_reason=self.failure_reason,
            hook=self.hook,
            main_narration=self.main_narration,
            project_g_comment=self.project_g_comment,
            closing=self.closing,
            full_narration=self.full_narration,
            evidence_snapshot=evidence,
            created_at=_as_utc(self.created_at),
            started_at=_as_utc_optional(self.started_at),
            completed_at=_as_utc_optional(self.completed_at),
            updated_at=_as_utc(self.updated_at),
        )
