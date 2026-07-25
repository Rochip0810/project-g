from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, Engine

from project_g.infrastructure.config import get_settings
from project_g.infrastructure.database import (
    Base,
    build_database_url,
    create_database_engine,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(
        config.config_file_name,
        disable_existing_loggers=False,
    )

target_metadata = Base.metadata


def _get_configured_database_url() -> str | None:
    configured_url = config.get_main_option("sqlalchemy.url") or ""
    normalized_url = configured_url.strip()

    return normalized_url or None


def _get_settings_database_url() -> str:
    settings = get_settings()

    return build_database_url(settings).render_as_string(
        hide_password=False,
    )


def _get_database_url() -> str:
    return _get_configured_database_url() or _get_settings_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _create_online_engine() -> Engine:
    configured_url = _get_configured_database_url()

    if configured_url is not None:
        return create_engine(
            configured_url,
            poolclass=pool.NullPool,
        )

    return create_database_engine(get_settings())


def run_migrations_online() -> None:
    connectable = _create_online_engine()

    try:
        with connectable.connect() as connection:
            _run_migrations(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
