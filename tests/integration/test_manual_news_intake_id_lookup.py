from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsSourceRepository,
)

_INTAKE_ID = UUID("33457bd2-cbf1-49db-9db1-9397c912fc39")
_SUBMITTED_AT = datetime(
    2026,
    8,
    5,
    13,
    0,
    tzinfo=UTC,
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
        session.rollback()


def test_repository_gets_intake_by_id(
    migrated_session: Session,
) -> None:
    source = NewsSource(
        source_id="metadata_cli_lookup_source",
        name="Metadata CLI Lookup Source",
        source_type=SourceType.WEBSITE,
        base_url=("https://lookup.example.com/news/"),
        is_official=False,
        status=SourceStatus.PAUSED,
        priority=1,
    )
    intake = ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id=source.source_id,
        submitted_url=("https://lookup.example.com/news/123/"),
        canonical_url=("https://lookup.example.com/news/123/"),
        submitted_at=_SUBMITTED_AT,
    )

    SqlAlchemyNewsSourceRepository(migrated_session).add(source)

    repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)
    repository.add(intake)
    migrated_session.expire_all()

    assert repository.get_by_intake_id(_INTAKE_ID) == intake
