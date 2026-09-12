from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from project_g.infrastructure.database import (
    get_current_revision,
)


def test_news_narration_audio_migration_upgrade_and_downgrade(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.upgrade(
        alembic_config,
        "0009_news_media_productions",
    )

    inspector = inspect(database_engine)

    assert "news_narration_audio_generations" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0009_news_media_productions")

    command.upgrade(
        alembic_config,
        "0010_narration_audio",
    )

    inspector = inspect(database_engine)

    assert get_current_revision(database_engine) == ("0010_narration_audio")
    assert "news_narration_audio_generations" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("news_narration_audio_generations")
    }

    assert set(columns) == {
        "audio_generation_id",
        "media_production_id",
        "audio_version",
        "status",
        "provider",
        "model",
        "voice",
        "audio_format",
        "source_text_sha256",
        "attempt_count",
        "storage_key",
        "byte_size",
        "content_sha256",
        "failure_reason",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }

    assert columns["audio_generation_id"]["nullable"] is False
    assert columns["media_production_id"]["nullable"] is False
    assert columns["audio_version"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["provider"]["nullable"] is False
    assert columns["model"]["nullable"] is False
    assert columns["voice"]["nullable"] is False
    assert columns["audio_format"]["nullable"] is False
    assert columns["source_text_sha256"]["nullable"] is False
    assert columns["attempt_count"]["nullable"] is False

    assert columns["storage_key"]["nullable"] is True
    assert columns["byte_size"]["nullable"] is True
    assert columns["content_sha256"]["nullable"] is True
    assert columns["failure_reason"]["nullable"] is True
    assert columns["started_at"]["nullable"] is True
    assert columns["completed_at"]["nullable"] is True

    unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("news_narration_audio_generations")
    }

    constraint = unique_constraints["uq_news_narration_audio_generations_media_version"]

    assert constraint["column_names"] == [
        "media_production_id",
        "audio_version",
    ]

    foreign_keys = inspector.get_foreign_keys("news_narration_audio_generations")

    assert len(foreign_keys) == 1
    assert foreign_keys[0]["name"] == ("fk_news_narration_audio_generations_media_production_id")
    assert foreign_keys[0]["referred_table"] == ("news_media_productions")
    assert foreign_keys[0]["constrained_columns"] == ["media_production_id"]
    assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"

    index_names = {
        index["name"] for index in inspector.get_indexes("news_narration_audio_generations")
    }

    assert "ix_news_narration_audio_generations_status_updated_at" in index_names

    check_constraint_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("news_narration_audio_generations")
    }

    assert {
        "ck_news_narration_audio_generations_status",
        "ck_news_narration_audio_generations_version",
        "ck_news_narration_audio_generations_attempt_count",
        "ck_news_narration_audio_generations_byte_size",
    } <= check_constraint_names

    command.downgrade(
        alembic_config,
        "0009_news_media_productions",
    )

    inspector = inspect(database_engine)

    assert "news_narration_audio_generations" not in inspector.get_table_names()
    assert get_current_revision(database_engine) == ("0009_news_media_productions")

    command.upgrade(
        alembic_config,
        "head",
    )
