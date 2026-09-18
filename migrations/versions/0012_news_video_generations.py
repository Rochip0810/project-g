"""Create the news_video_generations table."""

import sqlalchemy as sa
from alembic import op

revision = "0012_video_generation"
down_revision = "0011_character_dialogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_video_generations",
        sa.Column(
            "video_generation_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "media_production_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "video_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "renderer",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "video_format",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "width",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "height",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "fps",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "source_audio_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "storage_key",
            sa.String(length=1024),
            nullable=True,
        ),
        sa.Column(
            "byte_size",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "content_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "duration_ms",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'generating', 'generated', 'failed')",
            name="ck_news_video_generations_status",
        ),
        sa.CheckConstraint(
            "video_version >= 1",
            name="ck_news_video_generations_version",
        ),
        sa.CheckConstraint(
            "width >= 1",
            name="ck_news_video_generations_width",
        ),
        sa.CheckConstraint(
            "height >= 1",
            name="ck_news_video_generations_height",
        ),
        sa.CheckConstraint(
            "fps >= 1",
            name="ck_news_video_generations_fps",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_video_generations_attempt_count",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 1",
            name="ck_news_video_generations_byte_size",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 1",
            name="ck_news_video_generations_duration_ms",
        ),
        sa.ForeignKeyConstraint(
            ["media_production_id"],
            ["news_media_productions.media_production_id"],
            name="fk_news_video_generations_media_production_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "video_generation_id",
            name="pk_news_video_generations",
        ),
        sa.UniqueConstraint(
            "media_production_id",
            "video_version",
            name="uq_news_video_generations_media_version",
        ),
    )

    op.create_index(
        "ix_news_video_generations_status_updated_at",
        "news_video_generations",
        [
            "status",
            "updated_at",
            "video_generation_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_video_generations_status_updated_at",
        table_name="news_video_generations",
    )
    op.drop_table("news_video_generations")
