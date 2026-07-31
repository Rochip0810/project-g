"""Create the news_sources table."""

from alembic import op
import sqlalchemy as sa

revision = "0002_news_sources"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "base_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "is_official",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_news_sources_priority",
        ),
        sa.CheckConstraint(
            "source_type IN ('website', 'rss', 'api')",
            name="ck_news_sources_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('enabled', 'paused', 'disabled')",
            name="ck_news_sources_status",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_news_sources",
        ),
        sa.UniqueConstraint(
            "source_id",
            name="uq_news_sources_source_id",
        ),
    )

    op.create_index(
        "ix_news_sources_source_id",
        "news_sources",
        ["source_id"],
        unique=True,
    )
    op.create_index(
        "ix_news_sources_collectable_order",
        "news_sources",
        [
            "status",
            "is_official",
            "priority",
            "name",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_sources_collectable_order",
        table_name="news_sources",
    )
    op.drop_index(
        "ix_news_sources_source_id",
        table_name="news_sources",
    )
    op.drop_table("news_sources")
