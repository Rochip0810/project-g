"""Create the manual_news_intakes table."""

import sqlalchemy as sa
from alembic import op

revision = "0003_manual_news_intakes"
down_revision = "0002_news_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_news_intakes",
        sa.Column(
            "intake_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "submitted_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "canonical_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["news_sources.source_id"],
            name="fk_manual_news_intakes_source_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "intake_id",
            name="pk_manual_news_intakes",
        ),
        sa.UniqueConstraint(
            "canonical_url",
            name="uq_manual_news_intakes_canonical_url",
        ),
    )

    op.create_index(
        "ix_manual_news_intakes_source_submitted_at",
        "manual_news_intakes",
        [
            "source_id",
            "submitted_at",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_manual_news_intakes_source_submitted_at",
        table_name="manual_news_intakes",
    )
    op.drop_table("manual_news_intakes")
