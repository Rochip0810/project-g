"""Create the news_processing_jobs table."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0004_news_processing_jobs"
down_revision = "0003_manual_news_intakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_processing_jobs",
        sa.Column(
            "job_id",
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
            "attempt_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "last_error",
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
            ("status IN ('pending', 'processing', 'completed', 'failed')"),
            name="ck_news_processing_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_news_processing_jobs_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["manual_news_intakes.intake_id"],
            name="fk_news_processing_jobs_intake_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "job_id",
            name="pk_news_processing_jobs",
        ),
        sa.UniqueConstraint(
            "intake_id",
            name="uq_news_processing_jobs_intake_id",
        ),
    )

    op.create_index(
        "ix_news_processing_jobs_status_created_at",
        "news_processing_jobs",
        [
            "status",
            "created_at",
            "job_id",
        ],
        unique=False,
    )

    _backfill_existing_intakes()


def _backfill_existing_intakes() -> None:
    # Offline mode only generates migration SQL and has no
    # database connection from which existing rows can be read.
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
    processing_jobs = sa.table(
        "news_processing_jobs",
        sa.column("job_id", sa.Uuid()),
        sa.column("intake_id", sa.Uuid()),
        sa.column("status", sa.String(length=16)),
        sa.column("attempt_count", sa.Integer()),
        sa.column("last_error", sa.Text()),
        sa.column(
            "created_at",
            sa.DateTime(timezone=True),
        ),
        sa.column(
            "started_at",
            sa.DateTime(timezone=True),
        ),
        sa.column(
            "completed_at",
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
        sa.insert(processing_jobs),
        [
            {
                "job_id": uuid4(),
                "intake_id": row.intake_id,
                "status": "pending",
                "attempt_count": 0,
                "last_error": None,
                "created_at": (row.submitted_at or fallback_time),
                "started_at": None,
                "completed_at": None,
                "updated_at": (row.submitted_at or fallback_time),
            }
            for row in existing_intakes
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_processing_jobs_status_created_at",
        table_name="news_processing_jobs",
    )
    op.drop_table("news_processing_jobs")
