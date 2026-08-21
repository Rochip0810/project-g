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
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceDecision,
)
from project_g.infrastructure.database.repositories.manual_news_intakes import (
    SqlAlchemyManualNewsIntakeRepository,
)
from project_g.infrastructure.database.repositories.news_article_metadata import (
    SqlAlchemyNewsArticleMetadataRepository,
)
from project_g.infrastructure.database.repositories.news_priority_analyses import (
    SqlAlchemyNewsPriorityAnalysisRepository,
)
from project_g.infrastructure.database.repositories.news_ranking_candidates import (
    SqlAlchemyNewsRankingCandidateRepository,
)
from project_g.infrastructure.database.repositories.news_relevance_analyses import (
    SqlAlchemyNewsRelevanceAnalysisRepository,
)
from project_g.infrastructure.database.repositories.news_sources import (
    SqlAlchemyNewsSourceRepository,
)

_CREATED_AT = datetime(
    2026,
    8,
    21,
    10,
    0,
    tzinfo=UTC,
)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)
_PUBLISHED_AT = _CREATED_AT - timedelta(hours=1)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(
        alembic_config,
        "head",
    )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def _source() -> NewsSource:
    return NewsSource(
        source_id="hochi_giants_articles",
        name="Sports Hochi Giants",
        source_type=SourceType.WEBSITE,
        base_url="https://hochi.news/",
        is_official=False,
        status=SourceStatus.ENABLED,
        priority=92,
    )


def _seed_item(
    session: Session,
    *,
    number: int,
    decision: NewsRelevanceDecision,
    priority_state: str = "analyzed",
) -> UUID:
    intake_id = UUID(f"00000000-0000-0000-0000-{number:012d}")
    metadata_id = UUID(f"10000000-0000-0000-0000-{number:012d}")
    relevance_id = UUID(f"20000000-0000-0000-0000-{number:012d}")
    priority_id = UUID(f"30000000-0000-0000-0000-{number:012d}")

    intake = ManualNewsIntake(
        intake_id=intake_id,
        source_id="hochi_giants_articles",
        submitted_url=(f"https://hochi.news/articles/{number}"),
        canonical_url=(f"https://hochi.news/articles/{number}"),
        submitted_at=_CREATED_AT,
    )

    SqlAlchemyManualNewsIntakeRepository(session).add(intake)

    metadata = NewsArticleMetadata.pending(
        metadata_id=metadata_id,
        intake_id=intake_id,
        created_at=_CREATED_AT,
    ).record_manual(
        title=f"Giants ranking test {number}",
        published_at=_PUBLISHED_AT,
        description="Ranking candidate test.",
        updated_at=_UPDATED_AT,
    )

    SqlAlchemyNewsArticleMetadataRepository(session).add(
        NewsArticleMetadata.pending(
            metadata_id=metadata_id,
            intake_id=intake_id,
            created_at=_CREATED_AT,
        )
    )
    SqlAlchemyNewsArticleMetadataRepository(session).update(metadata)

    relevance = NewsRelevanceAnalysis.pending(
        analysis_id=relevance_id,
        intake_id=intake_id,
        created_at=_CREATED_AT,
    ).record_analyzed(
        relevance_score=90,
        decision=decision,
        reason="Ranking test relevance.",
        updated_at=_UPDATED_AT,
    )

    relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)
    relevance_repository.add(
        NewsRelevanceAnalysis.pending(
            analysis_id=relevance_id,
            intake_id=intake_id,
            created_at=_CREATED_AT,
        )
    )
    relevance_repository.update(relevance)

    priority_repository = SqlAlchemyNewsPriorityAnalysisRepository(session)

    pending_priority = NewsPriorityAnalysis.pending(
        analysis_id=priority_id,
        intake_id=intake_id,
        created_at=_CREATED_AT,
    )

    priority_repository.add(pending_priority)

    if priority_state == "analyzed":
        priority_repository.update(
            pending_priority.record_analyzed(
                priority_score=85,
                reason="Ranking test priority.",
                updated_at=_UPDATED_AT,
            )
        )
    elif priority_state == "failed":
        priority_repository.update(
            pending_priority.mark_failed(
                reason="Ranking test failure.",
                updated_at=_UPDATED_AT,
            )
        )
    elif priority_state != "pending":
        raise ValueError(f"Unknown priority_state: {priority_state}")

    return intake_id


def test_repository_returns_only_eligible_ranking_candidates(
    migrated_session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(migrated_session).add(_source())

    accepted_id = _seed_item(
        migrated_session,
        number=1,
        decision=NewsRelevanceDecision.ACCEPTED,
    )
    review_id = _seed_item(
        migrated_session,
        number=2,
        decision=NewsRelevanceDecision.REVIEW,
    )

    _seed_item(
        migrated_session,
        number=3,
        decision=NewsRelevanceDecision.REJECTED,
    )
    _seed_item(
        migrated_session,
        number=4,
        decision=NewsRelevanceDecision.ACCEPTED,
        priority_state="pending",
    )
    _seed_item(
        migrated_session,
        number=5,
        decision=NewsRelevanceDecision.ACCEPTED,
        priority_state="failed",
    )

    migrated_session.commit()

    repository = SqlAlchemyNewsRankingCandidateRepository(migrated_session)

    candidates = repository.list_eligible_candidates()

    candidate_ids = {candidate.intake_id for candidate in candidates}

    assert candidate_ids == {
        accepted_id,
        review_id,
    }

    assert all(candidate.relevance_score == 90 for candidate in candidates)
    assert all(candidate.priority_score == 85 for candidate in candidates)
    assert all(candidate.published_at == _PUBLISHED_AT for candidate in candidates)
