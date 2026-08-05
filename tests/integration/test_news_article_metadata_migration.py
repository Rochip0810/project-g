from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_article_metadata_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(
        alembic_config,
        "0004_news_processing_jobs",
    )

    inspector = inspect(database_engine)

    assert "news_article_metadata" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0004_news_processing_jobs")

    command.upgrade(
        alembic_config,
        "0005_news_article_metadata",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0005_news_article_metadata")
    assert "news_article_metadata" in inspector.get_table_names()

    column_names = {column["name"] for column in inspector.get_columns("news_article_metadata")}

    assert column_names == {
        "metadata_id",
        "intake_id",
        "status",
        "title",
        "published_at",
        "description",
        "failure_reason",
        "created_at",
        "updated_at",
    }

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("news_article_metadata")
    }

    assert "uq_news_article_metadata_intake_id" in unique_constraints

    foreign_keys = inspector.get_foreign_keys("news_article_metadata")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_article_metadata_intake_id")
    assert foreign_keys[0]["referred_table"] == ("manual_news_intakes")
    assert foreign_keys[0]["constrained_columns"] == ["intake_id"]

    index_names = {index["name"] for index in inspector.get_indexes("news_article_metadata")}

    assert "ix_news_article_metadata_status_updated_at" in index_names

    command.downgrade(
        alembic_config,
        "0004_news_processing_jobs",
    )

    inspector = inspect(database_engine)

    assert "news_article_metadata" not in inspector.get_table_names()

    command.upgrade(alembic_config, "head")
