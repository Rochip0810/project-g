from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.domain.news.processing_job import (
    NewsProcessingStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsProcessingJobRepository,
)
from project_g.interfaces.management.submit_news_url import (
    create_manual_intake_and_job,
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


def test_url_submission_creates_pending_processing_job(
    migrated_session: Session,
) -> None:
    submission = create_manual_intake_and_job(
        session=migrated_session,
        submitted_url=("https://www.giants.jp/news/987654/?utm_source=google#details"),
    )

    migrated_session.commit()
    migrated_session.expire_all()

    intake_repository = SqlAlchemyManualNewsIntakeRepository(migrated_session)
    job_repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)

    stored_intake = intake_repository.get_by_canonical_url("https://www.giants.jp/news/987654/")
    stored_job = job_repository.get_by_intake_id(submission.intake.intake_id)

    assert stored_intake == submission.intake
    assert stored_job == submission.processing_job
    assert stored_job is not None
    assert stored_job.status is NewsProcessingStatus.PENDING
    assert stored_job.attempt_count == 0
