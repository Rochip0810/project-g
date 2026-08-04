from datetime import UTC, datetime
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.processing_job import (
    NewsProcessingStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsProcessingJobRepository,
    SqlAlchemyNewsSourceRepository,
)

_INTAKE_ID = UUID("6d8539b9-d521-49c3-a3e8-7fc94240ef79")
_SUBMITTED_AT = datetime(
    2026,
    8,
    4,
    12,
    0,
    tzinfo=UTC,
)


def test_migration_backfills_existing_manual_intake(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(alembic_config, "base")

    try:
        command.upgrade(
            alembic_config,
            "0003_manual_news_intakes",
        )

        factory = sessionmaker(
            bind=database_engine,
            expire_on_commit=False,
        )

        with factory.begin() as session:
            SqlAlchemyNewsSourceRepository(session).add(
                NewsSource(
                    source_id="giants_official_news",
                    name="Giants Official News",
                    source_type=SourceType.WEBSITE,
                    base_url="https://www.giants.jp/news/",
                    is_official=True,
                    status=SourceStatus.PAUSED,
                    priority=100,
                )
            )

            SqlAlchemyManualNewsIntakeRepository(session).add(
                ManualNewsIntake(
                    intake_id=_INTAKE_ID,
                    source_id="giants_official_news",
                    submitted_url=("https://www.giants.jp/news/765432/"),
                    canonical_url=("https://www.giants.jp/news/765432/"),
                    submitted_at=_SUBMITTED_AT,
                )
            )

        command.upgrade(
            alembic_config,
            "0004_news_processing_jobs",
        )

        with factory() as session:
            job = SqlAlchemyNewsProcessingJobRepository(session).get_by_intake_id(_INTAKE_ID)

        assert job is not None
        assert job.intake_id == _INTAKE_ID
        assert job.status is NewsProcessingStatus.PENDING
        assert job.attempt_count == 0
        assert job.created_at == _SUBMITTED_AT
        assert job.updated_at == _SUBMITTED_AT
        assert job.started_at is None
        assert job.completed_at is None
        assert job.last_error is None
    finally:
        command.upgrade(alembic_config, "head")
