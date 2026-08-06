"""Create the news_article_metadata table."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0005_news_article_metadata"
down_revision = "0004_news_processing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_article_metadata",
        sa.Column(
            "metadata_id",
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
            "title",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "description",
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
            ("status IN ('pending', 'extracted', 'manual', 'unavailable', 'failed')"),
            name="ck_news_article_metadata_status",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_article_metadata_intake_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "metadata_id",
            name="pk_news_article_metadata",
        ),
        sa.UniqueConstraint(
            "intake_id",
            name="uq_news_article_metadata_intake_id",
        ),
    )

    op.create_index(
        "ix_news_article_metadata_status_updated_at",
        "news_article_metadata",
        [
            "status",
            "updated_at",
            "metadata_id",
        ],
        unique=False,
    )

    _backfill_existing_intakes()


def _backfill_existing_intakes() -> None:
    # Offline mode generates SQL without a live database.
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
    article_metadata = sa.table(
        "news_article_metadata",
        sa.column("metadata_id", sa.Uuid()),
        sa.column("intake_id", sa.Uuid()),
        sa.column("status", sa.String(length=16)),
        sa.column("title", sa.String(length=500)),
        sa.column(
            "published_at",
            sa.DateTime(timezone=True),
        ),
        sa.column("description", sa.Text()),
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
        sa.insert(article_metadata),
        [
            {
                "metadata_id": uuid4(),
                "intake_id": row.intake_id,
                "status": "pending",
                "title": None,
                "published_at": None,
                "description": None,
                "failure_reason": None,
                "created_at": (row.submitted_at or fallback_time),
                "updated_at": (row.submitted_at or fallback_time),
            }
            for row in existing_intakes
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_article_metadata_status_updated_at",
        table_name="news_article_metadata",
    )
    op.drop_table("news_article_metadata")
