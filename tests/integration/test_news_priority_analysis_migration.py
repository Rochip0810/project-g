from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_priority_analysis_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0006_news_relevance_analyses",
    )

    inspector = inspect(database_engine)

    assert "news_priority_analyses" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0006_news_relevance_analyses")

    command.upgrade(
        alembic_config,
        "0007_news_priority_analyses",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0007_news_priority_analyses")
    assert "news_priority_analyses" in inspector.get_table_names()

    column_names = {column["name"] for column in inspector.get_columns("news_priority_analyses")}

    assert column_names == {
        "analysis_id",
        "intake_id",
        "status",
        "priority_score",
        "reason",
        "failure_reason",
        "created_at",
        "updated_at",
    }

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("news_priority_analyses")
    }

    assert "uq_news_priority_analyses_intake_id" in unique_constraints

    foreign_keys = inspector.get_foreign_keys("news_priority_analyses")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_priority_analyses_intake_id")
    assert foreign_keys[0]["referred_table"] == ("manual_news_intakes")
    assert foreign_keys[0]["constrained_columns"] == ["intake_id"]

    index_names = {index["name"] for index in inspector.get_indexes("news_priority_analyses")}

    assert "ix_news_priority_analyses_status_updated_at" in index_names

    command.downgrade(
        alembic_config,
        "0006_news_relevance_analyses",
    )

    inspector = inspect(database_engine)

    assert "news_priority_analyses" not in inspector.get_table_names()

    command.upgrade(
        alembic_config,
        "head",
    )
