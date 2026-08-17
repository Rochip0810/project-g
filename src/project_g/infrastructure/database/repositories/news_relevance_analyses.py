from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)
from project_g.infrastructure.database.models import (
    NewsRelevanceAnalysisRecord,
)
from project_g.ports.repositories.news_relevance_analyses import (
    NewsRelevanceAnalysisAlreadyExistsError,
    NewsRelevanceAnalysisNotFoundError,
)


class SqlAlchemyNewsRelevanceAnalysisRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        if self.get_by_intake_id(analysis.intake_id) is not None:
            raise NewsRelevanceAnalysisAlreadyExistsError(analysis.intake_id)

        record = NewsRelevanceAnalysisRecord.from_domain(analysis)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsRelevanceAnalysisAlreadyExistsError(analysis.intake_id) from error

        return record.to_domain()

    def update(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        record = self._session.get(
            NewsRelevanceAnalysisRecord,
            analysis.analysis_id,
        )

        if record is None or record.intake_id != analysis.intake_id:
            raise NewsRelevanceAnalysisNotFoundError(analysis.analysis_id)

        record.status = analysis.status.value
        record.relevance_score = analysis.relevance_score
        record.decision = analysis.decision.value if analysis.decision is not None else None
        record.reason = analysis.reason
        record.failure_reason = analysis.failure_reason
        record.created_at = analysis.created_at
        record.updated_at = analysis.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        record = self._session.get(
            NewsRelevanceAnalysisRecord,
            analysis_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        statement = select(NewsRelevanceAnalysisRecord).where(
            NewsRelevanceAnalysisRecord.intake_id == intake_id
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()
