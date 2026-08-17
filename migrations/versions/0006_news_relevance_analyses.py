"""Create the news_relevance_analyses table."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0006_news_relevance_analyses"
down_revision = "0005_news_article_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_relevance_analyses",
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
            "relevance_score",
            sa.SmallInteger(),
            nullable=True,
        ),
        sa.Column(
            "decision",
            sa.String(length=16),
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
            name="ck_news_relevance_analyses_status",
        ),
        sa.CheckConstraint(
            ("decision IS NULL OR decision IN ('accepted', 'review', 'rejected')"),
            name="ck_news_relevance_analyses_decision",
        ),
        sa.CheckConstraint(
            ("relevance_score IS NULL OR relevance_score BETWEEN 0 AND 100"),
            name="ck_news_relevance_analyses_score",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_relevance_analyses_intake_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "analysis_id",
            name="pk_news_relevance_analyses",
        ),
        sa.UniqueConstraint(
            "intake_id",
            name="uq_news_relevance_analyses_intake_id",
        ),
    )

    op.create_index(
        "ix_news_relevance_analyses_status_updated_at",
        "news_relevance_analyses",
        [
            "status",
            "updated_at",
            "analysis_id",
        ],
        unique=False,
    )

    _backfill_existing_intakes()


def _backfill_existing_intakes() -> None:
    if op.get_context().as_sql:
        return

    connection = op.get_bind()

    manual_news_intakes = sa.table(
        "manual_news_intakes",
        sa.column("intake_id", sa.Uuid()),
        sa.column(
            "submitted_at",
            sa.DateTime(timezone=True),
        ),
    )

    relevance_analyses = sa.table(
        "news_relevance_analyses",
        sa.column("analysis_id", sa.Uuid()),
        sa.column("intake_id", sa.Uuid()),
        sa.column("status", sa.String(length=16)),
        sa.column("relevance_score", sa.SmallInteger()),
        sa.column("decision", sa.String(length=16)),
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

    existing_intakes = connection.execute(
        sa.select(
            manual_news_intakes.c.intake_id,
            manual_news_intakes.c.submitted_at,
        )
    ).all()

    if not existing_intakes:
        return

    fallback_time = datetime.now(UTC)

    connection.execute(
        sa.insert(relevance_analyses),
        [
            {
                "analysis_id": uuid4(),
                "intake_id": row.intake_id,
                "status": "pending",
                "relevance_score": None,
                "decision": None,
                "reason": None,
                "failure_reason": None,
                "created_at": (row.submitted_at or fallback_time),
                "updated_at": (row.submitted_at or fallback_time),
            }
            for row in existing_intakes
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_relevance_analyses_status_updated_at",
        table_name="news_relevance_analyses",
    )
    op.drop_table("news_relevance_analyses")
