"""Add character dialogue to news script generations."""

import sqlalchemy as sa
from alembic import op

revision = "0011_character_dialogue"
down_revision = "0010_narration_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_script_generations",
        sa.Column(
            "character_dialogue",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "news_script_generations",
        "character_dialogue",
    )
