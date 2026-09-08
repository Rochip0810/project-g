"""Create the news_script_generations table."""

import sqlalchemy as sa
from alembic import op

revision = "0008_news_script_generations"
down_revision = "0007_news_priority_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_script_generations",
        sa.Column(
            "generation_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "intake_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "generation_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "ranking_score",
            sa.SmallInteger(),
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
            "hook",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "main_narration",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "project_g_comment",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "closing",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "full_narration",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "evidence_snapshot",
            sa.JSON(),
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
            name="ck_news_script_generations_status",
        ),
        sa.CheckConstraint(
            "generation_version >= 1",
            name="ck_news_script_generations_version",
        ),
        sa.CheckConstraint(
            "ranking_score BETWEEN 0 AND 100",
            name="ck_news_script_generations_ranking_score",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_script_generations_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_script_generations_intake_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "generation_id",
            name="pk_news_script_generations",
        ),
        sa.UniqueConstraint(
            "intake_id",
            "generation_version",
            name="uq_news_script_generations_intake_version",
        ),
    )

    op.create_index(
        "ix_news_script_generations_status_updated_at",
        "news_script_generations",
        [
            "status",
            "updated_at",
            "generation_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_script_generations_status_updated_at",
        table_name="news_script_generations",
    )
    op.drop_table("news_script_generations")
