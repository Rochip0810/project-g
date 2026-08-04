from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_processing_job_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(
        alembic_config,
        "0003_manual_news_intakes",
    )

    inspector = inspect(database_engine)

    assert "news_processing_jobs" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0003_manual_news_intakes")

    command.upgrade(
        alembic_config,
        "0004_news_processing_jobs",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0004_news_processing_jobs")
    assert "news_processing_jobs" in inspector.get_table_names()

    column_names = {column["name"] for column in inspector.get_columns("news_processing_jobs")}

    assert column_names == {
        "job_id",
        "intake_id",
        "status",
        "attempt_count",
        "last_error",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("news_processing_jobs")
    }

    assert "uq_news_processing_jobs_intake_id" in unique_constraints

    foreign_keys = inspector.get_foreign_keys("news_processing_jobs")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_processing_jobs_intake_id")
    assert foreign_keys[0]["referred_table"] == ("manual_news_intakes")
    assert foreign_keys[0]["constrained_columns"] == ["intake_id"]

    index_names = {index["name"] for index in inspector.get_indexes("news_processing_jobs")}

    assert "ix_news_processing_jobs_status_created_at" in index_names

    command.downgrade(
        alembic_config,
        "0003_manual_news_intakes",
    )

    inspector = inspect(database_engine)

    assert "news_processing_jobs" not in inspector.get_table_names()

    command.upgrade(alembic_config, "head")
