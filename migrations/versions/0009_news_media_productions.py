"""Create the news_media_productions table."""

import sqlalchemy as sa
from alembic import op

revision = "0009_news_media_productions"
down_revision = "0008_news_script_generations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_media_productions",
        sa.Column(
            "media_production_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "script_generation_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "media_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
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
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_news_media_productions_status",
        ),
        sa.CheckConstraint(
            "media_version >= 1",
            name="ck_news_media_productions_version",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_media_productions_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["script_generation_id"],
            ["news_script_generations.generation_id"],
            name="fk_news_media_productions_script_generation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "media_production_id",
            name="pk_news_media_productions",
        ),
        sa.UniqueConstraint(
            "script_generation_id",
            "media_version",
            name="uq_news_media_productions_script_version",
        ),
    )

    op.create_index(
        "ix_news_media_productions_status_updated_at",
        "news_media_productions",
        [
            "status",
            "updated_at",
            "media_production_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_media_productions_status_updated_at",
        table_name="news_media_productions",
    )
    op.drop_table("news_media_productions")
