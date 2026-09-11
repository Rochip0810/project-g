from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_media_production_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0008_news_script_generations",
    )

    inspector = inspect(database_engine)

    assert "news_media_productions" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0008_news_script_generations")

    command.upgrade(
        alembic_config,
        "0009_news_media_productions",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0009_news_media_productions")
    assert "news_media_productions" in inspector.get_table_names()

    columns = {column["name"]: column for column in inspector.get_columns("news_media_productions")}

    assert set(columns) == {
        "media_production_id",
        "script_generation_id",
        "media_version",
        "status",
        "attempt_count",
        "failure_reason",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }

    assert columns["media_production_id"]["nullable"] is False
    assert columns["script_generation_id"]["nullable"] is False
    assert columns["media_version"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["attempt_count"]["nullable"] is False
    assert columns["failure_reason"]["nullable"] is True
    assert columns["started_at"]["nullable"] is True
    assert columns["completed_at"]["nullable"] is True

    unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("news_media_productions")
    }

    constraint = unique_constraints["uq_news_media_productions_script_version"]

    assert constraint["column_names"] == [
        "script_generation_id",
        "media_version",
    ]

    foreign_keys = inspector.get_foreign_keys("news_media_productions")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_media_productions_script_generation_id")
    assert foreign_keys[0]["referred_table"] == ("news_script_generations")
    assert foreign_keys[0]["constrained_columns"] == ["script_generation_id"]

    index_names = {index["name"] for index in inspector.get_indexes("news_media_productions")}

    assert "ix_news_media_productions_status_updated_at" in index_names

    check_constraint_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("news_media_productions")
    }

    assert {
        "ck_news_media_productions_status",
        "ck_news_media_productions_version",
        "ck_news_media_productions_attempt_count",
    } <= check_constraint_names

    command.downgrade(
        alembic_config,
        "0008_news_script_generations",
    )

    inspector = inspect(database_engine)

    assert "news_media_productions" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0008_news_script_generations")

    command.upgrade(
        alembic_config,
        "head",
    )
