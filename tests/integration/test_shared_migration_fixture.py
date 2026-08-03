from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
    is_database_at_head,
)


def test_shared_migration_fixtures_are_isolated(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    assert get_current_revision(database_engine) is None

    command.upgrade(alembic_config, "head")

    assert get_current_revision(database_engine) == ("0003_manual_news_intakes")
    assert is_database_at_head(
        database_engine,
        alembic_config,
    )

    command.downgrade(alembic_config, "base")

    assert get_current_revision(database_engine) is None
