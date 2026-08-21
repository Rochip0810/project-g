from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)
from project_g.ports.repositories.news_priority_analyses import (
    NewsPriorityAnalysisAlreadyExistsError,
    NewsPriorityAnalysisRepository,
)

Clock = Callable[[], datetime]
AnalysisIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateNewsPriorityAnalysis:
    def __init__(
        self,
        *,
        repository: NewsPriorityAnalysisRepository,
        clock: Clock = _utc_now,
        analysis_id_factory: AnalysisIdFactory = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._analysis_id_factory = analysis_id_factory

    def execute(
        self,
        intake_id: UUID,
    ) -> NewsPriorityAnalysis:
        existing = self._repository.get_by_intake_id(intake_id)

        if existing is not None:
            raise NewsPriorityAnalysisAlreadyExistsError(intake_id)

        analysis = NewsPriorityAnalysis.pending(
            analysis_id=self._analysis_id_factory(),
            intake_id=intake_id,
            created_at=self._clock(),
        )

        return self._repository.add(analysis)
