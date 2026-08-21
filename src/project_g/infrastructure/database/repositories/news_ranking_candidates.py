from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from project_g.domain.news.article_metadata import (
    NewsMetadataStatus,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityStatus,
)
from project_g.domain.news.ranking import (
    NewsRankingCandidate,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.infrastructure.database.models import (
    NewsArticleMetadataRecord,
    NewsPriorityAnalysisRecord,
    NewsRelevanceAnalysisRecord,
)


def _as_utc_optional(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


class SqlAlchemyNewsRankingCandidateRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def list_eligible_candidates(
        self,
    ) -> list[NewsRankingCandidate]:
        statement = (
            select(
                NewsArticleMetadataRecord.intake_id,
                NewsArticleMetadataRecord.title,
                NewsArticleMetadataRecord.published_at,
                NewsRelevanceAnalysisRecord.relevance_score,
                NewsPriorityAnalysisRecord.priority_score,
            )
            .join(
                NewsRelevanceAnalysisRecord,
                NewsRelevanceAnalysisRecord.intake_id == NewsArticleMetadataRecord.intake_id,
            )
            .join(
                NewsPriorityAnalysisRecord,
                NewsPriorityAnalysisRecord.intake_id == NewsArticleMetadataRecord.intake_id,
            )
            .where(
                NewsArticleMetadataRecord.status.in_(
                    [
                        NewsMetadataStatus.EXTRACTED.value,
                        NewsMetadataStatus.MANUAL.value,
                    ]
                ),
                NewsArticleMetadataRecord.title.is_not(None),
                NewsRelevanceAnalysisRecord.status == NewsRelevanceStatus.ANALYZED.value,
                NewsRelevanceAnalysisRecord.decision.in_(
                    [
                        NewsRelevanceDecision.ACCEPTED.value,
                        NewsRelevanceDecision.REVIEW.value,
                    ]
                ),
                NewsRelevanceAnalysisRecord.relevance_score.is_not(None),
                NewsPriorityAnalysisRecord.status == NewsPriorityStatus.ANALYZED.value,
                NewsPriorityAnalysisRecord.priority_score.is_not(None),
            )
        )

        rows = self._session.execute(statement).all()

        candidates: list[NewsRankingCandidate] = []

        for row in rows:
            title = row.title
            relevance_score = row.relevance_score
            priority_score = row.priority_score

            if title is None or relevance_score is None or priority_score is None:
                continue

            candidates.append(
                NewsRankingCandidate(
                    intake_id=row.intake_id,
                    title=title,
                    published_at=_as_utc_optional(row.published_at),
                    relevance_score=relevance_score,
                    priority_score=priority_score,
                )
            )

        return candidates
