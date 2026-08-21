from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.create_priority_analysis import (
    CreateNewsPriorityAnalysis,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)
from project_g.ports.repositories.news_priority_analyses import (
    NewsPriorityAnalysisAlreadyExistsError,
    NewsPriorityAnalysisNotFoundError,
)

_ANALYSIS_ID = UUID("a35293c1-1c1a-48d7-b52c-d8dfe434cc13")
_INTAKE_ID = UUID("170aff1d-d13f-4acb-9f33-69366bbab990")
_CREATED_AT = datetime(
    2026,
    8,
    21,
    6,
    0,
    tzinfo=UTC,
)


class FakeNewsPriorityAnalysisRepository:
    def __init__(self) -> None:
        self._by_analysis_id: dict[
            UUID,
            NewsPriorityAnalysis,
        ] = {}
        self._by_intake_id: dict[
            UUID,
            NewsPriorityAnalysis,
        ] = {}
        self.added: list[NewsPriorityAnalysis] = []

    def add(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        if analysis.intake_id in self._by_intake_id:
            raise NewsPriorityAnalysisAlreadyExistsError(analysis.intake_id)

        self._by_analysis_id[analysis.analysis_id] = analysis
        self._by_intake_id[analysis.intake_id] = analysis
        self.added.append(analysis)

        return analysis

    def update(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        if analysis.analysis_id not in self._by_analysis_id:
            raise NewsPriorityAnalysisNotFoundError(analysis.analysis_id)

        self._by_analysis_id[analysis.analysis_id] = analysis
        self._by_intake_id[analysis.intake_id] = analysis

        return analysis

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        return self._by_analysis_id.get(analysis_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        return self._by_intake_id.get(intake_id)


def _service(
    repository: FakeNewsPriorityAnalysisRepository,
) -> CreateNewsPriorityAnalysis:
    return CreateNewsPriorityAnalysis(
        repository=repository,
        clock=lambda: _CREATED_AT,
        analysis_id_factory=lambda: _ANALYSIS_ID,
    )


def test_service_creates_pending_analysis() -> None:
    repository = FakeNewsPriorityAnalysisRepository()

    analysis = _service(repository).execute(_INTAKE_ID)

    assert analysis.analysis_id == _ANALYSIS_ID
    assert analysis.intake_id == _INTAKE_ID
    assert analysis.status is NewsPriorityStatus.PENDING
    assert analysis.priority_score is None
    assert analysis.reason is None
    assert analysis.failure_reason is None
    assert analysis.created_at == _CREATED_AT
    assert analysis.updated_at == _CREATED_AT
    assert repository.added == [analysis]


def test_service_rejects_duplicate_intake_analysis() -> None:
    repository = FakeNewsPriorityAnalysisRepository()
    service = _service(repository)

    first = service.execute(_INTAKE_ID)

    with pytest.raises(
        NewsPriorityAnalysisAlreadyExistsError,
        match="already exists",
    ):
        service.execute(_INTAKE_ID)

    assert repository.added == [first]


def test_repository_returns_analysis_by_intake() -> None:
    repository = FakeNewsPriorityAnalysisRepository()

    created = _service(repository).execute(_INTAKE_ID)

    assert repository.get_by_intake_id(_INTAKE_ID) == created
    assert repository.get_by_analysis_id(_ANALYSIS_ID) == created
