"""Create the news_priority_analyses table."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0007_news_priority_analyses"
down_revision = "0006_news_relevance_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_priority_analyses",
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "intake_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "priority_score",
            sa.SmallInteger(),
            nullable=True,
        ),
        sa.Column(
            "reason",
            sa.Text(),
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
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'analyzed', 'failed')",
            name="ck_news_priority_analyses_status",
        ),
        sa.CheckConstraint(
            "priority_score IS NULL OR priority_score BETWEEN 0 AND 100",
            name="ck_news_priority_analyses_score",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_priority_analyses_intake_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "analysis_id",
            name="pk_news_priority_analyses",
        ),
        sa.UniqueConstraint(
            "intake_id",
            name="uq_news_priority_analyses_intake_id",
        ),
    )

    op.create_index(
        "ix_news_priority_analyses_status_updated_at",
        "news_priority_analyses",
        [
            "status",
            "updated_at",
            "analysis_id",
        ],
        unique=False,
    )

    _backfill_eligible_relevance_analyses()


def _backfill_eligible_relevance_analyses() -> None:
    if op.get_context().as_sql:
        return

    connection = op.get_bind()

    relevance_analyses = sa.table(
        "news_relevance_analyses",
        sa.column("intake_id", sa.Uuid()),
        sa.column("status", sa.String(length=16)),
        sa.column("decision", sa.String(length=16)),
        sa.column(
            "updated_at",
            sa.DateTime(timezone=True),
        ),
    )

    priority_analyses = sa.table(
        "news_priority_analyses",
        sa.column("analysis_id", sa.Uuid()),
        sa.column("intake_id", sa.Uuid()),
        sa.column("status", sa.String(length=16)),
        sa.column("priority_score", sa.SmallInteger()),
        sa.column("reason", sa.Text()),
        sa.column("failure_reason", sa.Text()),
        sa.column(
            "created_at",
            sa.DateTime(timezone=True),
        ),
        sa.column(
            "updated_at",
            sa.DateTime(timezone=True),
        ),
    )

    eligible_rows = connection.execute(
        sa.select(
            relevance_analyses.c.intake_id,
            relevance_analyses.c.updated_at,
        ).where(
            relevance_analyses.c.status == "analyzed",
            relevance_analyses.c.decision.in_(
                [
                    "accepted",
                    "review",
                ]
            ),
        )
    ).all()

    if not eligible_rows:
        return

    fallback_time = datetime.now(UTC)

    connection.execute(
        sa.insert(priority_analyses),
        [
            {
                "analysis_id": uuid4(),
                "intake_id": row.intake_id,
                "status": "pending",
                "priority_score": None,
                "reason": None,
                "failure_reason": None,
                "created_at": (row.updated_at or fallback_time),
                "updated_at": (row.updated_at or fallback_time),
            }
            for row in eligible_rows
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_priority_analyses_status_updated_at",
        table_name="news_priority_analyses",
    )
    op.drop_table("news_priority_analyses")
