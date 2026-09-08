from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_script_generation_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0007_news_priority_analyses",
    )

    inspector = inspect(database_engine)

    assert "news_script_generations" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0007_news_priority_analyses")

    command.upgrade(
        alembic_config,
        "0008_news_script_generations",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0008_news_script_generations")
    assert "news_script_generations" in inspector.get_table_names()

    columns = {
        column["name"]: column for column in inspector.get_columns("news_script_generations")
    }

    assert set(columns) == {
        "generation_id",
        "intake_id",
        "generation_version",
        "status",
        "ranking_score",
        "attempt_count",
        "failure_reason",
        "hook",
        "main_narration",
        "project_g_comment",
        "closing",
        "full_narration",
        "evidence_snapshot",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }

    assert columns["generation_id"]["nullable"] is False
    assert columns["intake_id"]["nullable"] is False
    assert columns["generation_version"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["ranking_score"]["nullable"] is False
    assert columns["attempt_count"]["nullable"] is False
    assert columns["evidence_snapshot"]["nullable"] is True

    unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("news_script_generations")
    }

    constraint = unique_constraints["uq_news_script_generations_intake_version"]

    assert constraint["column_names"] == [
        "intake_id",
        "generation_version",
    ]

    foreign_keys = inspector.get_foreign_keys("news_script_generations")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_script_generations_intake_id")
    assert foreign_keys[0]["referred_table"] == ("manual_news_intakes")
    assert foreign_keys[0]["constrained_columns"] == ["intake_id"]

    index_names = {index["name"] for index in inspector.get_indexes("news_script_generations")}

    assert "ix_news_script_generations_status_updated_at" in index_names

    check_constraint_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("news_script_generations")
    }

    assert {
        "ck_news_script_generations_status",
        "ck_news_script_generations_version",
        "ck_news_script_generations_ranking_score",
        "ck_news_script_generations_attempt_count",
    } <= check_constraint_names

    command.downgrade(
        alembic_config,
        "0007_news_priority_analyses",
    )

    inspector = inspect(database_engine)

    assert "news_script_generations" not in inspector.get_table_names()

    command.upgrade(
        alembic_config,
        "head",
    )
