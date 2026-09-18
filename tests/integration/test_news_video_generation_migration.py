from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_video_generation_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0011_character_dialogue",
    )

    inspector = inspect(database_engine)

    assert "news_video_generations" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0011_character_dialogue")

    command.upgrade(
        alembic_config,
        "0012_video_generation",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0012_video_generation")
    assert "news_video_generations" in inspector.get_table_names()

    columns = {column["name"]: column for column in inspector.get_columns("news_video_generations")}

    assert set(columns) == {
        "video_generation_id",
        "media_production_id",
        "video_version",
        "status",
        "renderer",
        "video_format",
        "width",
        "height",
        "fps",
        "source_audio_sha256",
        "attempt_count",
        "storage_key",
        "byte_size",
        "content_sha256",
        "duration_ms",
        "failure_reason",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }

    for name in {
        "video_generation_id",
        "media_production_id",
        "video_version",
        "status",
        "renderer",
        "video_format",
        "width",
        "height",
        "fps",
        "source_audio_sha256",
        "attempt_count",
        "created_at",
        "updated_at",
    }:
        assert columns[name]["nullable"] is False

    for name in {
        "storage_key",
        "byte_size",
        "content_sha256",
        "duration_ms",
        "failure_reason",
        "started_at",
        "completed_at",
    }:
        assert columns[name]["nullable"] is True

    unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("news_video_generations")
    }

    constraint = unique_constraints["uq_news_video_generations_media_version"]

    assert constraint["column_names"] == [
        "media_production_id",
        "video_version",
    ]

    foreign_keys = inspector.get_foreign_keys("news_video_generations")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_video_generations_media_production_id")
    assert foreign_keys[0]["referred_table"] == ("news_media_productions")
    assert foreign_keys[0]["constrained_columns"] == ["media_production_id"]
    assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"

    index_names = {index["name"] for index in inspector.get_indexes("news_video_generations")}

    assert "ix_news_video_generations_status_updated_at" in index_names

    check_constraint_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("news_video_generations")
    }

    assert {
        "ck_news_video_generations_status",
        "ck_news_video_generations_version",
        "ck_news_video_generations_width",
        "ck_news_video_generations_height",
        "ck_news_video_generations_fps",
        "ck_news_video_generations_attempt_count",
        "ck_news_video_generations_byte_size",
        "ck_news_video_generations_duration_ms",
    } <= check_constraint_names

    command.downgrade(
        alembic_config,
        "0011_character_dialogue",
    )

    inspector = inspect(database_engine)

    assert "news_video_generations" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0011_character_dialogue")

    command.upgrade(
        alembic_config,
        "head",
    )
