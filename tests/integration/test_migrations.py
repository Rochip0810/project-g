from io import StringIO
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine

from project_g.infrastructure.database import (
    create_alembic_config,
    get_current_revision,
    get_head_revision,
    is_database_at_head,
)


def _create_sqlite_url(tmp_path: Path) -> str:
    database_path = tmp_path / "migration-test.db"

    return f"sqlite+pysqlite:///{database_path.as_posix()}"


def test_alembic_configuration_contains_no_database_password() -> None:
    config = create_alembic_config()

    assert config.config_file_name is not None

    config_contents = Path(config.config_file_name).read_text(
        encoding="utf-8",
    )

    assert "sqlalchemy.url =" in config_contents
    assert "DATABASE_PASSWORD" not in config_contents
    assert "postgresql+psycopg://" not in config_contents


def test_initial_head_revision_is_available() -> None:
    config = create_alembic_config()

    assert get_head_revision(config) == "0004_news_processing_jobs"


def test_upgrade_to_head_and_downgrade_to_base(
    tmp_path: Path,
) -> None:
    database_url = _create_sqlite_url(tmp_path)
    config = create_alembic_config(database_url)
    engine = create_engine(database_url)

    try:
        assert get_current_revision(engine) is None
        assert is_database_at_head(engine, config) is False

        command.upgrade(config, "head")

        assert get_current_revision(engine) == "0004_news_processing_jobs"
        assert is_database_at_head(engine, config) is True

        command.downgrade(config, "base")

        assert get_current_revision(engine) is None
        assert is_database_at_head(engine, config) is False
    finally:
        engine.dispose()


def test_offline_upgrade_generates_sql() -> None:
    output = StringIO()

    config = create_alembic_config(
        "sqlite+pysqlite:///:memory:",
        output_buffer=output,
    )

    command.upgrade(
        config,
        "head",
        sql=True,
    )

    generated_sql = output.getvalue()

    assert "CREATE TABLE alembic_version" in generated_sql
    assert "0004_news_processing_jobs" in generated_sql
