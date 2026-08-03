from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_manual_news_intake_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    # Start from a known revision regardless of the
    # database state left by another migration test.
    command.downgrade(alembic_config, "base")
    command.upgrade(
        alembic_config,
        "0002_news_sources",
    )

    inspector = inspect(database_engine)

    assert "manual_news_intakes" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == "0002_news_sources"

    command.upgrade(alembic_config, "head")

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == "0003_manual_news_intakes"
    assert "manual_news_intakes" in inspector.get_table_names()

    column_names = {column["name"] for column in inspector.get_columns("manual_news_intakes")}

    assert column_names == {
        "intake_id",
        "source_id",
        "submitted_url",
        "canonical_url",
        "submitted_at",
    }

    unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("manual_news_intakes")
    }

    assert "uq_manual_news_intakes_canonical_url" in unique_constraints

    foreign_keys = inspector.get_foreign_keys("manual_news_intakes")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_manual_news_intakes_source_id")
    assert foreign_keys[0]["referred_table"] == ("news_sources")
    assert foreign_keys[0]["constrained_columns"] == ["source_id"]
    assert foreign_keys[0]["referred_columns"] == ["source_id"]

    command.downgrade(
        alembic_config,
        "0002_news_sources",
    )

    inspector = inspect(database_engine)

    assert "manual_news_intakes" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == "0002_news_sources"

    # Restore the database for tests that run afterward.
    command.upgrade(alembic_config, "head")

    assert get_current_revision(database_engine) == "0003_manual_news_intakes"
