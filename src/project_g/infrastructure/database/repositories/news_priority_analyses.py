from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)
from project_g.infrastructure.database.models import (
    NewsPriorityAnalysisRecord,
)
from project_g.ports.repositories.news_priority_analyses import (
    NewsPriorityAnalysisAlreadyExistsError,
    NewsPriorityAnalysisNotFoundError,
)


class SqlAlchemyNewsPriorityAnalysisRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        if self.get_by_intake_id(analysis.intake_id) is not None:
            raise NewsPriorityAnalysisAlreadyExistsError(analysis.intake_id)

        record = NewsPriorityAnalysisRecord.from_domain(analysis)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsPriorityAnalysisAlreadyExistsError(analysis.intake_id) from error

        return record.to_domain()

    def update(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        record = self._session.get(
            NewsPriorityAnalysisRecord,
            analysis.analysis_id,
        )

        if record is None or record.intake_id != analysis.intake_id:
            raise NewsPriorityAnalysisNotFoundError(analysis.analysis_id)

        record.status = analysis.status.value
        record.priority_score = analysis.priority_score
        record.reason = analysis.reason
        record.failure_reason = analysis.failure_reason
        record.created_at = analysis.created_at
        record.updated_at = analysis.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        record = self._session.get(
            NewsPriorityAnalysisRecord,
            analysis_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        statement = select(NewsPriorityAnalysisRecord).where(
            NewsPriorityAnalysisRecord.intake_id == intake_id
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()
