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
from project_g.domain.news.article_metadata import (
    NewsMetadataStatus,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsSourceRepository,
)

_INTAKE_ID = UUID("9ab481b1-2c04-41a4-820a-1d364302ef72")
_SUBMITTED_AT = datetime(
    2026,
    8,
    5,
    18,
    0,
    tzinfo=UTC,
)


def test_migration_backfills_existing_intake_metadata(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(alembic_config, "base")

    try:
        command.upgrade(
            alembic_config,
            "0004_news_processing_jobs",
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
                    submitted_url=("https://www.giants.jp/news/246810/"),
                    canonical_url=("https://www.giants.jp/news/246810/"),
                    submitted_at=_SUBMITTED_AT,
                )
            )

        command.upgrade(
            alembic_config,
            "0005_news_article_metadata",
        )

        with factory() as session:
            metadata = SqlAlchemyNewsArticleMetadataRepository(session).get_by_intake_id(_INTAKE_ID)

        assert metadata is not None
        assert metadata.intake_id == _INTAKE_ID
        assert metadata.status is NewsMetadataStatus.PENDING
        assert metadata.title is None
        assert metadata.published_at is None
        assert metadata.description is None
        assert metadata.failure_reason is None
        assert metadata.created_at == _SUBMITTED_AT
        assert metadata.updated_at == _SUBMITTED_AT
    finally:
        command.upgrade(alembic_config, "head")
