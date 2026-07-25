from pathlib import Path
from typing import TextIO

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ALEMBIC_CONFIG_PATH = _PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_DIRECTORY = _PROJECT_ROOT / "migrations"


def _escape_config_value(value: str) -> str:
    return value.replace("%", "%%")


def create_alembic_config(
    database_url: str | None = None,
    *,
    output_buffer: TextIO | None = None,
) -> Config:
    config = Config(
        _ALEMBIC_CONFIG_PATH,
        output_buffer=output_buffer,
    )

    config.set_main_option(
        "script_location",
        str(_MIGRATIONS_DIRECTORY),
    )

    if database_url is not None:
        config.set_main_option(
            "sqlalchemy.url",
            _escape_config_value(database_url),
        )

    return config


def get_head_revision(config: Config | None = None) -> str:
    resolved_config = config if config is not None else create_alembic_config()

    script_directory = ScriptDirectory.from_config(resolved_config)
    head_revision = script_directory.get_current_head()

    if head_revision is None:
        raise RuntimeError("Alembic head revision is not configured")

    return head_revision


def get_current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)

        return migration_context.get_current_revision()


def is_database_at_head(
    engine: Engine,
    config: Config | None = None,
) -> bool:
    return get_current_revision(engine) == get_head_revision(config)
