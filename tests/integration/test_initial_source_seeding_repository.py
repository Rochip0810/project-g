from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news import (
    seed_initial_news_sources,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyNewsSourceRepository,
)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def test_initial_sources_are_persisted_idempotently(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)

    first_result = seed_initial_news_sources(repository)
    migrated_session.commit()

    second_result = seed_initial_news_sources(repository)

    assert first_result.added_count == 7
    assert second_result.added_count == 0
    assert second_result.existing_count == 7
    assert len(repository.list_all()) == 7


def test_collectable_sources_follow_editorial_priority(
    migrated_session: Session,
) -> None:
    repository = SqlAlchemyNewsSourceRepository(migrated_session)

    seed_initial_news_sources(repository)

    assert tuple(source.source_id for source in repository.list_collectable()) == (
        "giants_official_schedule",
        "npb_official_schedule",
        "npb_official_stats",
        "hochi_giants_x",
        "hochi_giants_articles",
    )
