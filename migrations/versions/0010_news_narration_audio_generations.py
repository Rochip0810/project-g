"""Create the news_narration_audio_generations table."""

import sqlalchemy as sa
from alembic import op

revision = "0010_narration_audio"
down_revision = "0009_news_media_productions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_narration_audio_generations",
        sa.Column(
            "audio_generation_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "media_production_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "audio_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "model",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "voice",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "audio_format",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "source_text_sha256",
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
            name="ck_news_narration_audio_generations_status",
        ),
        sa.CheckConstraint(
            "audio_version >= 1",
            name="ck_news_narration_audio_generations_version",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_narration_audio_generations_attempt_count",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 1",
            name="ck_news_narration_audio_generations_byte_size",
        ),
        sa.ForeignKeyConstraint(
            ["media_production_id"],
            ["news_media_productions.media_production_id"],
            name="fk_news_narration_audio_generations_media_production_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "audio_generation_id",
            name="pk_news_narration_audio_generations",
        ),
        sa.UniqueConstraint(
            "media_production_id",
            "audio_version",
            name="uq_news_narration_audio_generations_media_version",
        ),
    )

    op.create_index(
        "ix_news_narration_audio_generations_status_updated_at",
        "news_narration_audio_generations",
        [
            "status",
            "updated_at",
            "audio_generation_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_narration_audio_generations_status_updated_at",
        table_name="news_narration_audio_generations",
    )
    op.drop_table("news_narration_audio_generations")
