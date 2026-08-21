from datetime import UTC, datetime, timedelta
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
from project_g.domain.news.priority_analysis import (
    NewsPriorityStatus,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceDecision,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsPriorityAnalysisRepository,
    SqlAlchemyNewsRelevanceAnalysisRepository,
    SqlAlchemyNewsSourceRepository,
)

_SOURCE_ID = "giants_official_news"

_ACCEPTED_ID = UUID("10000000-0000-0000-0000-000000000001")
_REVIEW_ID = UUID("10000000-0000-0000-0000-000000000002")
_REJECTED_ID = UUID("10000000-0000-0000-0000-000000000003")
_PENDING_ID = UUID("10000000-0000-0000-0000-000000000004")
_FAILED_ID = UUID("10000000-0000-0000-0000-000000000005")

_SUBMITTED_AT = datetime(
    2026,
    8,
    21,
    0,
    0,
    tzinfo=UTC,
)


def _intake(
    *,
    intake_id: UUID,
    number: int,
) -> ManualNewsIntake:
    url = f"https://www.giants.jp/news/{number}/"

    return ManualNewsIntake(
        intake_id=intake_id,
        source_id=_SOURCE_ID,
        submitted_url=url,
        canonical_url=url,
        submitted_at=_SUBMITTED_AT,
    )


def test_priority_migration_backfills_only_eligible_relevance_analyses(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    command.downgrade(
        alembic_config,
        "base",
    )

    try:
        command.upgrade(
            alembic_config,
            "0006_news_relevance_analyses",
        )

        factory = sessionmaker(
            bind=database_engine,
            expire_on_commit=False,
        )

        with factory.begin() as session:
            source_repository = SqlAlchemyNewsSourceRepository(session)
            intake_repository = SqlAlchemyManualNewsIntakeRepository(session)
            relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)

            source_repository.add(
                NewsSource(
                    source_id=_SOURCE_ID,
                    name="Giants Official News",
                    source_type=SourceType.WEBSITE,
                    base_url="https://www.giants.jp/news/",
                    is_official=True,
                    status=SourceStatus.PAUSED,
                    priority=100,
                )
            )

            intake_repository.add(
                _intake(
                    intake_id=_ACCEPTED_ID,
                    number=100001,
                )
            )
            intake_repository.add(
                _intake(
                    intake_id=_REVIEW_ID,
                    number=100002,
                )
            )
            intake_repository.add(
                _intake(
                    intake_id=_REJECTED_ID,
                    number=100003,
                )
            )
            intake_repository.add(
                _intake(
                    intake_id=_PENDING_ID,
                    number=100004,
                )
            )
            intake_repository.add(
                _intake(
                    intake_id=_FAILED_ID,
                    number=100005,
                )
            )

            accepted = NewsRelevanceAnalysis.pending(
                analysis_id=UUID("20000000-0000-0000-0000-000000000001"),
                intake_id=_ACCEPTED_ID,
                created_at=_SUBMITTED_AT,
            ).record_analyzed(
                relevance_score=95,
                decision=NewsRelevanceDecision.ACCEPTED,
                reason="Direct Giants news",
                updated_at=_SUBMITTED_AT + timedelta(minutes=1),
            )

            review = NewsRelevanceAnalysis.pending(
                analysis_id=UUID("20000000-0000-0000-0000-000000000002"),
                intake_id=_REVIEW_ID,
                created_at=_SUBMITTED_AT,
            ).record_analyzed(
                relevance_score=55,
                decision=NewsRelevanceDecision.REVIEW,
                reason="Secondary Giants connection",
                updated_at=_SUBMITTED_AT + timedelta(minutes=2),
            )

            rejected = NewsRelevanceAnalysis.pending(
                analysis_id=UUID("20000000-0000-0000-0000-000000000003"),
                intake_id=_REJECTED_ID,
                created_at=_SUBMITTED_AT,
            ).record_analyzed(
                relevance_score=15,
                decision=NewsRelevanceDecision.REJECTED,
                reason="Weak Giants connection",
                updated_at=_SUBMITTED_AT + timedelta(minutes=3),
            )

            pending = NewsRelevanceAnalysis.pending(
                analysis_id=UUID("20000000-0000-0000-0000-000000000004"),
                intake_id=_PENDING_ID,
                created_at=_SUBMITTED_AT,
            )

            failed = NewsRelevanceAnalysis.pending(
                analysis_id=UUID("20000000-0000-0000-0000-000000000005"),
                intake_id=_FAILED_ID,
                created_at=_SUBMITTED_AT,
            ).mark_failed(
                reason="AI request failed",
                updated_at=_SUBMITTED_AT + timedelta(minutes=4),
            )

            relevance_repository.add(accepted)
            relevance_repository.add(review)
            relevance_repository.add(rejected)
            relevance_repository.add(pending)
            relevance_repository.add(failed)

        command.upgrade(
            alembic_config,
            "0007_news_priority_analyses",
        )

        with factory() as session:
            priority_repository = SqlAlchemyNewsPriorityAnalysisRepository(session)

            accepted_priority = priority_repository.get_by_intake_id(_ACCEPTED_ID)
            review_priority = priority_repository.get_by_intake_id(_REVIEW_ID)
            rejected_priority = priority_repository.get_by_intake_id(_REJECTED_ID)
            pending_priority = priority_repository.get_by_intake_id(_PENDING_ID)
            failed_priority = priority_repository.get_by_intake_id(_FAILED_ID)

        assert accepted_priority is not None
        assert accepted_priority.status is NewsPriorityStatus.PENDING
        assert accepted_priority.priority_score is None
        assert accepted_priority.reason is None
        assert accepted_priority.failure_reason is None
        assert accepted_priority.created_at == (_SUBMITTED_AT + timedelta(minutes=1))

        assert review_priority is not None
        assert review_priority.status is NewsPriorityStatus.PENDING
        assert review_priority.priority_score is None
        assert review_priority.reason is None
        assert review_priority.failure_reason is None
        assert review_priority.created_at == (_SUBMITTED_AT + timedelta(minutes=2))

        assert rejected_priority is None
        assert pending_priority is None
        assert failed_priority is None
    finally:
        command.upgrade(
            alembic_config,
            "head",
        )
