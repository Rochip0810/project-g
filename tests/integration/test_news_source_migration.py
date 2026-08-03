from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_source_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0001_baseline",
    )

    inspector = inspect(database_engine)

    assert "news_sources" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0001_baseline")

    command.upgrade(
        alembic_config,
        "0002_news_sources",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0002_news_sources")
    assert "news_sources" in inspector.get_table_names()

    column_names = {column["name"] for column in inspector.get_columns("news_sources")}

    assert column_names == {
        "id",
        "source_id",
        "name",
        "source_type",
        "base_url",
        "is_official",
        "status",
        "priority",
        "created_at",
        "updated_at",
    }

    command.downgrade(
        alembic_config,
        "0001_baseline",
    )

    inspector = inspect(database_engine)

    assert "news_sources" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0001_baseline")
