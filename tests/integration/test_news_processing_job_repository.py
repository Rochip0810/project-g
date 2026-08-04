from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsProcessingJobRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    NewsProcessingJobAlreadyExistsError,
    NewsProcessingJobNotFoundError,
)

_JOB_1_ID = UUID("12d23129-41c5-4616-a360-feb42d52845a")
_JOB_2_ID = UUID("f292bf80-f5d6-498d-a1de-a163b884b8b5")
_JOB_3_ID = UUID("aad7e854-247f-4426-8319-54c468b29070")

_INTAKE_1_ID = UUID("33b8166b-2bee-49f7-ab41-caa4968d9266")
_INTAKE_2_ID = UUID("bf5db7ca-e0bd-4b71-81d6-13b14bd4d84d")
_INTAKE_3_ID = UUID("a8e78ca0-9d94-4661-af67-a926461ef24a")

_BASE_TIME = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


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


def _source() -> NewsSource:
    return NewsSource(
        source_id="giants_official_news",
        name="Giants Official News",
        source_type=SourceType.WEBSITE,
        base_url="https://www.giants.jp/news/",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=100,
    )


def _intake(
    *,
    intake_id: UUID,
    article_number: int,
) -> ManualNewsIntake:
    url = f"https://www.giants.jp/news/{article_number}/"

    return ManualNewsIntake(
        intake_id=intake_id,
        source_id="giants_official_news",
        submitted_url=url,
        canonical_url=url,
        submitted_at=_BASE_TIME,
    )


def _job(
    *,
    job_id: UUID,
    intake_id: UUID,
    created_at: datetime,
) -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=job_id,
        intake_id=intake_id,
        created_at=created_at,
    )


def _seed_source_and_intakes(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())

    repository = SqlAlchemyManualNewsIntakeRepository(session)

    repository.add(
        _intake(
            intake_id=_INTAKE_1_ID,
            article_number=10001,
        )
    )
    repository.add(
        _intake(
            intake_id=_INTAKE_2_ID,
            article_number=10002,
        )
    )
    repository.add(
        _intake(
            intake_id=_INTAKE_3_ID,
            article_number=10003,
        )
    )


def test_repository_adds_and_retrieves_job(
    migrated_session: Session,
) -> None:
    _seed_source_and_intakes(migrated_session)
    repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)
    job = _job(
        job_id=_JOB_1_ID,
        intake_id=_INTAKE_1_ID,
        created_at=_BASE_TIME,
    )

    stored = repository.add(job)
    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == job
    assert repository.get_by_job_id(job.job_id) == job
    assert repository.get_by_intake_id(job.intake_id) == job


def test_repository_updates_job_status(
    migrated_session: Session,
) -> None:
    _seed_source_and_intakes(migrated_session)
    repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)
    pending = _job(
        job_id=_JOB_1_ID,
        intake_id=_INTAKE_1_ID,
        created_at=_BASE_TIME,
    )
    repository.add(pending)

    processing = pending.start(started_at=_BASE_TIME + timedelta(minutes=1))
    stored = repository.update(processing)

    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_job_id(processing.job_id)

    assert stored.status is NewsProcessingStatus.PROCESSING
    assert stored.attempt_count == 1
    assert loaded == processing


def test_repository_rejects_duplicate_intake_job(
    migrated_session: Session,
) -> None:
    _seed_source_and_intakes(migrated_session)
    repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)

    repository.add(
        _job(
            job_id=_JOB_1_ID,
            intake_id=_INTAKE_1_ID,
            created_at=_BASE_TIME,
        )
    )

    with pytest.raises(NewsProcessingJobAlreadyExistsError):
        repository.add(
            _job(
                job_id=_JOB_2_ID,
                intake_id=_INTAKE_1_ID,
                created_at=_BASE_TIME,
            )
        )


def test_repository_returns_oldest_pending_job(
    migrated_session: Session,
) -> None:
    _seed_source_and_intakes(migrated_session)
    repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)

    processing = _job(
        job_id=_JOB_1_ID,
        intake_id=_INTAKE_1_ID,
        created_at=_BASE_TIME,
    ).start(started_at=_BASE_TIME + timedelta(minutes=1))
    newer_pending = _job(
        job_id=_JOB_2_ID,
        intake_id=_INTAKE_2_ID,
        created_at=_BASE_TIME + timedelta(minutes=3),
    )
    older_pending = _job(
        job_id=_JOB_3_ID,
        intake_id=_INTAKE_3_ID,
        created_at=_BASE_TIME + timedelta(minutes=2),
    )

    repository.add(processing)
    repository.add(newer_pending)
    repository.add(older_pending)

    assert repository.get_oldest_pending() == (older_pending)


def test_repository_update_rejects_unknown_job(
    migrated_session: Session,
) -> None:
    _seed_source_and_intakes(migrated_session)
    repository = SqlAlchemyNewsProcessingJobRepository(migrated_session)
    job = _job(
        job_id=_JOB_1_ID,
        intake_id=_INTAKE_1_ID,
        created_at=_BASE_TIME,
    )

    with pytest.raises(NewsProcessingJobNotFoundError):
        repository.update(job)
