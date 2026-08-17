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
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsRelevanceAnalysisRepository,
    SqlAlchemyNewsSourceRepository,
)

_INTAKE_ID = UUID("36f08c70-d877-4994-b23f-a3dd2113b767")
_SUBMITTED_AT = datetime(
    2026,
    8,
    12,
    12,
    0,
    tzinfo=UTC,
)


def test_migration_backfills_existing_intake_relevance_analysis(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(alembic_config, "base")

    try:
        command.upgrade(
            alembic_config,
            "0005_news_article_metadata",
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
                    submitted_url=("https://www.giants.jp/news/135790/"),
                    canonical_url=("https://www.giants.jp/news/135790/"),
                    submitted_at=_SUBMITTED_AT,
                )
            )

        command.upgrade(
            alembic_config,
            "0006_news_relevance_analyses",
        )

        with factory() as session:
            analysis = SqlAlchemyNewsRelevanceAnalysisRepository(session).get_by_intake_id(
                _INTAKE_ID
            )

        assert analysis is not None
        assert analysis.intake_id == _INTAKE_ID
        assert analysis.status is NewsRelevanceStatus.PENDING
        assert analysis.relevance_score is None
        assert analysis.decision is None
        assert analysis.reason is None
        assert analysis.failure_reason is None
        assert analysis.created_at == _SUBMITTED_AT
        assert analysis.updated_at == _SUBMITTED_AT
    finally:
        command.upgrade(alembic_config, "head")
